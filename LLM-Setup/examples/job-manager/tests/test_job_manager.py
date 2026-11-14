#!/usr/bin/env python3
"""Unit tests for job manager."""

import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.job_manager import JobManager, JobStatus


class TestJobManager(unittest.TestCase):
    """Test cases for JobManager."""

    def setUp(self):
        self.manager = JobManager(simulation_mode=True)

    def tearDown(self):
        self.manager.close()

    def test_create_job(self):
        """Test job creation with UUIDv4."""
        job = self.manager.create_job("test_job", "NVIDIA-GPU", "model-v1")
        self.assertIsNotNone(job.id)
        self.assertEqual(job.name, "test_job")
        self.assertEqual(job.backend, "NVIDIA-GPU")
        self.assertEqual(job.model, "model-v1")
        self.assertEqual(job.status, JobStatus.QUEUED)

    def test_job_id_is_uuid(self):
        """Test that job ID is a valid UUID."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        import uuid
        self.assertTrue(uuid.UUID(job.id))

    def test_get_job(self):
        """Test retrieving job by ID."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        retrieved = self.manager.get_job(job.id)
        self.assertEqual(retrieved.id, job.id)

    def test_get_all_jobs(self):
        """Test getting all jobs."""
        job1 = self.manager.create_job("job1", "NVIDIA-GPU", "model1")
        self.manager.create_job("job2", "AMD-GPU", "model2")
        jobs = self.manager.get_all_jobs()
        self.assertEqual(len(jobs), 2)

    def test_get_jobs_by_status(self):
        """Test filtering jobs by status."""
        job1 = self.manager.create_job("job1", "NVIDIA-GPU", "model1")
        self.manager.start_job(job1)
        self.manager.complete_job(job1, "{}")
        completed = self.manager.get_jobs_by_status(JobStatus.COMPLETED)
        self.assertEqual(len(completed), 1)

    def test_get_jobs_by_backend(self):
        """Test filtering jobs by backend."""
        self.manager.create_job("nvidia_gpu_job", "NVIDIA-GPU", "model")
        self.manager.create_job("amd_gpu_job", "AMD-GPU", "model")
        nvidia_gpu_jobs = self.manager.get_jobs_by_backend("NVIDIA-GPU")
        amd_gpu_jobs = self.manager.get_jobs_by_backend("AMD-GPU")
        self.assertEqual(len(nvidia_gpu_jobs), 1)
        self.assertEqual(len(amd_gpu_jobs), 1)

    def test_start_job(self):
        """Test starting a queued job."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.assertTrue(self.manager.start_job(job))
        self.assertEqual(job.status, JobStatus.RUNNING)

    def test_start_failed_job(self):
        """Test that starting non-queued job fails."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.manager.start_job(job)
        self.assertFalse(self.manager.start_job(job))

    def test_complete_job(self):
        """Test completing a running job."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.manager.start_job(job)
        self.assertTrue(self.manager.complete_job(job, '{"status": "ok"}'))
        self.assertEqual(job.status, JobStatus.COMPLETED)

    def test_fail_job(self):
        """Test failing a running job."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.manager.start_job(job)
        self.assertTrue(self.manager.fail_job(job, "Test error"))
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIsNotNone(job.error)

    def test_retry_job(self):
        """Test retrying a failed job."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model", max_retries=3)
        self.manager.start_job(job)
        self.manager.fail_job(job, "Error 1")
        self.assertTrue(self.manager.retry_job(job))
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.status, JobStatus.QUEUED)

    def test_retry_exceeds_max(self):
        """Test that retry stops after max retries."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model", max_retries=2)
        self.manager.start_job(job)
        self.manager.fail_job(job, "Error")
        self.assertTrue(self.manager.retry_job(job))
        self.manager.start_job(job); self.manager.fail_job(job, "Again")
        self.assertTrue(self.manager.retry_job(job))
        self.manager.start_job(job); self.manager.fail_job(job, "Final")
        self.assertFalse(self.manager.retry_job(job))
        self.assertEqual(job.retry_count, 2)

    def test_cancel_job(self):
        """Test cancelling a job."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.assertTrue(self.manager.cancel_job(job))
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error, "Cancelled")

    def test_dashboard_data(self):
        """Test dashboard data structure."""
        job1 = self.manager.create_job("job1", "NVIDIA-GPU", "model1")
        self.manager.create_job("job2", "AMD-GPU", "model2")
        self.manager.start_job(job1)
        self.manager.complete_job(job1, "{}")
        data = self.manager.get_dashboard_data()
        self.assertIn("total_jobs", data)
        self.assertIn("queued", data)
        self.assertIn("running", data)
        self.assertIn("completed", data)
        self.assertIn("failed", data)
        self.assertIn("nvidia_gpu_jobs", data)
        self.assertIn("amd_gpu_jobs", data)
        self.assertIn("jobs", data)

    def test_job_history_persistence(self):
        """Test that job history is persisted to SQLite."""
        job = self.manager.create_job("test", "NVIDIA-GPU", "model")
        self.manager.start_job(job)
        self.manager.complete_job(job, "{}")
        # Verify job exists in database
        import sqlite3
        conn = self.manager._conn
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (job.id,))
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
