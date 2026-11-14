#!/usr/bin/env python3
"""Integration tests for job management system."""

import unittest
import sys
import os
import tempfile
import sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.job_manager import JobManager, JobStatus


class TestIntegration(unittest.TestCase):
    """Integration tests for job manager with SQLite persistence."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "jobs.db")
        self.manager = JobManager(db_path=self.db_path, simulation_mode=True)

    def tearDown(self):
        self.manager.close()
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_restart_preserves_jobs_and_history(self):
        job = self.manager.create_job("persisted", "NVIDIA-GPU", "model", max_retries=2)
        self.manager.start_job(job); self.manager.complete_job(job, "verified-local-result")
        self.manager.close()
        self.manager = JobManager(self.db_path, simulation_mode=True)
        restored = self.manager.get_job(job.id)
        self.assertEqual(restored.status, JobStatus.COMPLETED)
        self.assertEqual(restored.receipt, "verified-local-result")
        self.assertEqual(restored.max_retries, 2)
        self.assertEqual(self.manager._conn.execute("SELECT count(*) FROM job_history WHERE job_id=?", (job.id,)).fetchone()[0], 3)

    def test_full_job_lifecycle(self):
        """Test complete job lifecycle with persistence."""
        job = self.manager.create_job("integration_test", "NVIDIA-GPU", "model-v1")
        self.assertEqual(job.status, JobStatus.QUEUED)

        self.manager.start_job(job)
        self.assertEqual(job.status, JobStatus.RUNNING)

        self.manager.complete_job(job, '{"result": "success"}')
        self.assertEqual(job.status, JobStatus.COMPLETED)

        # Verify persistence
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM jobs WHERE id = ?", (job.id,))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "completed")

    def test_multiple_backends(self):
        """Test jobs across NVIDIA-GPU and AMD-GPU backends."""
        nvidia_gpu_job = self.manager.create_job("nvidia_gpu_task", "NVIDIA-GPU", "nvidia-gpu-model")
        amd_gpu_job = self.manager.create_job("amd_gpu_task", "AMD-GPU", "amd-gpu-model")

        self.manager.start_job(nvidia_gpu_job)
        self.manager.complete_job(nvidia_gpu_job, "{}")

        self.manager.start_job(amd_gpu_job)
        self.manager.complete_job(amd_gpu_job, "{}")

        data = self.manager.get_dashboard_data()
        self.assertEqual(data["nvidia_gpu_jobs"], 1)
        self.assertEqual(data["amd_gpu_jobs"], 1)

    def test_retry_with_backoff(self):
        """Test retry logic with exponential backoff."""
        job = self.manager.create_job("retry_test", "NVIDIA-GPU", "model", max_retries=3)

        # Simulate failures
        for i in range(3):
            self.manager.start_job(job)
            self.manager.fail_job(job, f"Error {i}")
            self.assertTrue(self.manager.retry_job(job))

        # Should fail after max retries
        self.manager.start_job(job)
        self.manager.fail_job(job, "Final error")
        self.assertFalse(self.manager.retry_job(job))
        self.assertEqual(job.retry_count, 3)

    def test_job_history(self):
        """Test job history persistence."""
        job = self.manager.create_job("history_test", "NVIDIA-GPU", "model")

        self.manager.start_job(job)
        self.manager.fail_job(job, "First failure")
        self.manager.retry_job(job)
        self.manager.start_job(job)
        self.manager.complete_job(job, "{}")

        # Verify history table has entries
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM job_history WHERE job_id = ?", (job.id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    def test_dashboard_completeness(self):
        """Test dashboard includes all required fields."""
        d1 = self.manager.create_job("d1", "NVIDIA-GPU", "m1")
        self.manager.create_job("d2", "AMD-GPU", "m2")
        self.manager.start_job(d1)
        self.manager.complete_job(d1, "{}")

        data = self.manager.get_dashboard_data()

        # Check status counts
        self.assertIn("total_jobs", data)
        self.assertIn("queued", data)
        self.assertIn("running", data)
        self.assertIn("completed", data)
        self.assertIn("failed", data)

        # Check job details
        for job in data["jobs"]:
            self.assertIn("id", job)
            self.assertIn("name", job)
            self.assertIn("status", job)
            self.assertIn("backend", job)
            self.assertIn("model", job)
            self.assertIn("created_at", job)
            self.assertIn("receipt", job)

    def test_concurrent_operations(self):
        """Test concurrent job operations."""
        import threading
        import time

        jobs_created = []
        jobs_completed = []

        def create_and_complete():
            job = self.manager.create_job(f"concurrent_{len(jobs_created)}", "NVIDIA-GPU", "model")
            jobs_created.append(job.id)
            time.sleep(0.01)
            self.manager.start_job(job)
            time.sleep(0.01)
            self.manager.complete_job(job, "{}")
            jobs_completed.append(job.id)

        threads = [threading.Thread(target=create_and_complete) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(jobs_created), 5)
        self.assertEqual(len(jobs_completed), 5)


if __name__ == "__main__":
    unittest.main()
