#!/usr/bin/env python3
"""Dashboard for job management system showing all specialists and job status."""

import json
from typing import Dict, Any, List
from src.job_manager import JobManager, JobStatus


def format_dashboard(manager: JobManager) -> str:
    """Format and return dashboard data as JSON."""
    data = manager.get_dashboard_data()
    return json.dumps(data, indent=2)


def print_dashboard(manager: JobManager):
    """Print dashboard to stdout."""
    print(format_dashboard(manager))


if __name__ == "__main__":
    from src.job_manager import JobManager
    manager = JobManager(simulation_mode=True)
    print_dashboard(manager)
