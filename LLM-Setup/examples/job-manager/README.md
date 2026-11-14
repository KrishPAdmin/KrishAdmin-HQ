# Durable Job Management Prototype

SQLite-based job queue management for NVIDIA-GPU and AMD-GPU backends with exponential backoff retry logic.

## Features

- UUIDv4 request IDs for each job
- SQLite-based persistence for job queues and history
- Exponential backoff retry logic
- Simulation mode for testing
- JSON dashboard output from local stored jobs
- Stored job status, backend/model labels, timestamps and caller-supplied results

## Current scope and limitations

The repaired increment passes 22 tests covering lifecycle, persistence, restart recovery, retry bounds and concurrent use of one manager instance. It is not the complete requested control center. A real web UI, seven-person team view, live read-only integration, per-GPU scheduler/concurrency enforcement, client-supplied idempotency keys, and ambiguous-outcome recovery remain unimplemented. Stored receipt text is supplied by the caller; this prototype does not verify GPU execution. Simulation mode skips retry sleeps and does not execute model inference. No infrastructure deployment was performed.

The initial generated tests had invalid name-versus-ID lookups and tried retrying an already queued job. These were corrected alongside the implementation; tests were not weakened to accept broken lifecycle behavior.

## Quick Start

```bash
# Run unit tests
python3 tests/test_job_manager.py

# Run integration tests
python3 tests/test_integration.py

# Run all tests
python3 -m unittest discover -s tests

# Run demo
python3 src/job_manager.py
```

## API Usage

```python
from src.job_manager import JobManager, JobStatus

# Create manager (use file path for persistence)
manager = JobManager(db_path="jobs.db", simulation_mode=False)

# Create a job
job = manager.create_job("my_task", "NVIDIA-GPU", "model-v1")

# Start the job
manager.start_job(job)

# Complete the job
manager.complete_job(job, '{"result": "success"}')

# Get dashboard data
data = manager.get_dashboard_data()
print(data)
```

## File Structure

```
src/
  job_manager.py    # Core job management logic
  dashboard.py      # Dashboard formatting
tests/
  test_job_manager.py   # Unit tests
  test_integration.py   # Integration tests
README.md              # This file
```

## Requirements

- Python 3.8+
- Standard library only (no external dependencies)

## License

Internal use only.
