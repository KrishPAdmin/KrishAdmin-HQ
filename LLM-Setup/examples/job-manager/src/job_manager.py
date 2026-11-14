#!/usr/bin/env python3
"""Durable job management prototype with SQLite-based queues."""

import sqlite3
import uuid
import time
import json
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field, asdict
from pathlib import Path


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    name: str
    status: JobStatus
    backend: str
    model: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    receipt: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    delay_seconds: int = 2  # Exponential backoff base


class JobManager:
    """Manages durable jobs with SQLite persistence and exponential backoff."""

    def __init__(self, db_path: str = ":memory:", simulation_mode: bool = False):
        self.db_path = db_path
        self.simulation_mode = simulation_mode
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self._init_db()
        self._conn.row_factory = sqlite3.Row
        for row in self._conn.execute("SELECT * FROM jobs"):
            values = dict(row); values["status"] = JobStatus(values["status"])
            self._jobs[values["id"]] = Job(**values)

    def close(self):
        with self._lock:
            self._conn.close()

    def _init_db(self):
        """Initialize SQLite database schema."""
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error TEXT,
                receipt TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                delay_seconds INTEGER DEFAULT 2
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_history (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT
            )
        """)
        self._conn.commit()

    def _generate_receipt(self, job: Job) -> str:
        """Generate execution receipt for a job."""
        receipt_data = {
            "job_id": job.id,
            "name": job.name,
            "backend": job.backend,
            "model": job.model,
            "status": job.status,
            "completed_at": job.completed_at,
            "retry_count": job.retry_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(receipt_data, indent=2)

    def create_job(self, name: str, backend: str, model: str,
                   max_retries: int = 3, delay_seconds: int = 2) -> Job:
        """Create a new job with UUIDv4 request ID."""
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            name=name,
            status=JobStatus.QUEUED,
            backend=backend,
            model=model,
            created_at=datetime.now(timezone.utc).isoformat(),
            max_retries=max_retries, delay_seconds=delay_seconds
        )
        with self._lock:
            self._jobs[job_id] = job
            self._persist_job(job)
            for callback in self._callbacks.get("on_job_created", []): callback(job)
        return job

    def _persist_job(self, job: Job):
        """Persist job to SQLite."""
        conn = self._conn
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO jobs
            (id, name, status, backend, model, created_at, started_at,
             completed_at, error, receipt, retry_count, max_retries, delay_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id, job.name, job.status.value, job.backend, job.model,
            job.created_at, job.started_at, job.completed_at,
            job.error, job.receipt, job.retry_count, job.max_retries,
            job.delay_seconds
        ))
        cursor.execute("""
            INSERT OR REPLACE INTO job_history
            (id, job_id, status, timestamp, details)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), job.id, job.status.value,
            datetime.now(timezone.utc).isoformat(), json.dumps(asdict(job))
        ))
        conn.commit()


    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> List[Job]:
        """Get all jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        """Get jobs by status."""
        with self._lock:
            return [j for j in self._jobs.values() if j.status == status]

    def get_jobs_by_backend(self, backend: str) -> List[Job]:
        """Get jobs by backend (NVIDIA-GPU or AMD-GPU)."""
        with self._lock:
            return [j for j in self._jobs.values() if j.backend == backend]

    def get_jobs_by_model(self, model: str) -> List[Job]:
        """Get jobs by model."""
        with self._lock:
            return [j for j in self._jobs.values() if j.model == model]

    def start_job(self, job: Job) -> bool:
        """Start a queued job."""
        with self._lock:
            if job.status != JobStatus.QUEUED:
                return False
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc).isoformat()
            self._persist_job(job)
            return True


    def complete_job(self, job: Job, receipt: str) -> bool:
        """Complete a running job."""
        with self._lock:
            if job.status != JobStatus.RUNNING:
                return False
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.receipt = receipt
            self._persist_job(job)
            for callback in self._callbacks.get("on_job_completed", []): callback(job)
            return True


    def fail_job(self, job: Job, error: str) -> bool:
        """Fail a running job."""
        with self._lock:
            if job.status != JobStatus.RUNNING:
                return False
            job.status = JobStatus.FAILED
            job.error = error
            job.completed_at = datetime.now(timezone.utc).isoformat()
            self._persist_job(job)
            for callback in self._callbacks.get("on_job_failed", []): callback(job)
            return True


    def retry_job(self, job: Job) -> bool:
        """Retry a failed job with exponential backoff."""
        with self._lock:
            if job.status != JobStatus.FAILED:
                return False
            if job.retry_count >= job.max_retries:
                return False  # Max retries exceeded
            job.retry_count += 1
            job.status = JobStatus.QUEUED
            job.started_at = None
            job.completed_at = None
            job.receipt = None
            job.error = None
            self._persist_job(job)
            delay = job.delay_seconds * (2 ** (job.retry_count - 1))
            if not self.simulation_mode:
                time.sleep(delay)
            return True


    def cancel_job(self, job: Job) -> bool:
        """Cancel a queued or running job."""
        with self._lock:
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                job.status = JobStatus.FAILED
                job.error = "Cancelled"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                self._persist_job(job)
                return True
            return False


    def register_callback(self, event: str, callback: Callable):
        """Register a callback for job events."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get dashboard data showing all jobs and assignments."""
        jobs = self.get_all_jobs()
        return {
            "total_jobs": len(jobs),
            "queued": len(self.get_jobs_by_status(JobStatus.QUEUED)),
            "running": len(self.get_jobs_by_status(JobStatus.RUNNING)),
            "completed": len(self.get_jobs_by_status(JobStatus.COMPLETED)),
            "failed": len(self.get_jobs_by_status(JobStatus.FAILED)),
            "nvidia_gpu_jobs": len(self.get_jobs_by_backend("NVIDIA-GPU")),
            "amd_gpu_jobs": len(self.get_jobs_by_backend("AMD-GPU")),
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "status": j.status.value,
                    "backend": j.backend,
                    "model": j.model,
                    "created_at": j.created_at,
                    "started_at": j.started_at,
                    "completed_at": j.completed_at,
                    "error": j.error,
                    "receipt": j.receipt,
                    "retry_count": j.retry_count
                }
                for j in jobs
            ]
        }


if __name__ == "__main__":
    # Demo usage
    manager = JobManager(simulation_mode=True)
    job = manager.create_job("test_job", "NVIDIA-GPU", "model-v1")
    print(f"Created job: {job.id}")
    manager.start_job(job)
    print(f"Started job: {job.id}")
    manager.complete_job(job, '{"status": "success"}')
    print(f"Completed job: {job.id}")
    print(manager.get_dashboard_data())
