# Iridium-main/app/api/schemas/dashboard.py

from datetime import datetime
from typing import List

from pydantic import BaseModel

class RecentJob(BaseModel):
    """Defines the structure for a single job in the recent activity list."""

    id: int
    original_filename: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class JobStatusCounts(BaseModel):
    """Holds the counts for jobs broken down by status."""

    awaiting_validation: int
    completed: int
    submission_failed: int
    processing: int
    other: int


class DashboardStats(BaseModel):
    """The main response model for the entire dashboard statistics endpoint."""

class DashboardStats(BaseModel):
    """The main response model for the entire dashboard statistics endpoint."""
    jobs_today: int
    jobs_this_week: int
    status_counts: JobStatusCounts
    recent_jobs: List[RecentJob]
