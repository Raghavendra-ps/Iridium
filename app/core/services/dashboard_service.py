# Iridium-main/app/core/services/dashboard_service.py

from datetime import datetime, timedelta

from app.api.schemas.dashboard import DashboardStats, JobStatusCounts, RecentJob
from app.db.models import ConversionJob
from sqlalchemy import case, func
from sqlalchemy.orm import Session


def get_dashboard_stats(*, db: Session, owner_id: int | None = None) -> DashboardStats:
    """
    Retrieves and aggregates key performance indicators for the user's dashboard.
    If owner_id is None, returns global stats (for Managers/Superadmins).
    """
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=now.weekday())

    # Helper to apply owner filter
    def apply_owner_filter(q):
        return q.filter(ConversionJob.owner_id == owner_id) if owner_id else q

    # Query for jobs created today and this week
    jobs_today = apply_owner_filter(db.query(ConversionJob).filter(ConversionJob.created_at >= today_start)).count()
    jobs_this_week = apply_owner_filter(db.query(ConversionJob).filter(ConversionJob.created_at >= week_start)).count()

    # Status Counts
    status_counts_query = (
        db.query(
            func.sum(case((ConversionJob.status == "AWAITING_VALIDATION", 1), else_=0)).label("awaiting_validation"),
            func.sum(case((ConversionJob.status == "COMPLETED", 1), else_=0)).label("completed"),
            func.sum(case((ConversionJob.status == "SUBMISSION_FAILED", 1), else_=0)).label("submission_failed"),
            func.sum(
                case(
                    (
                        ConversionJob.status.in_(
                            ["PROCESSING", "UPLOADED", "PENDING_SUBMISSION", "SUBMITTING"]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("processing"),
            func.sum(
                case(
                    (
                        ~ConversionJob.status.in_(
                            [
                                "AWAITING_VALIDATION",
                                "COMPLETED",
                                "SUBMISSION_FAILED",
                                "PROCESSING",
                                "UPLOADED",
                                "PENDING_SUBMISSION",
                                "SUBMITTING",
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("other"),
        )
    )
    
    if owner_id:
        status_counts_query = status_counts_query.filter(ConversionJob.owner_id == owner_id)
        
    status_counts_result = status_counts_query.one()

    status_counts = JobStatusCounts(
        awaiting_validation=status_counts_result.awaiting_validation or 0,
        completed=status_counts_result.completed or 0,
        submission_failed=status_counts_result.submission_failed or 0,
        processing=status_counts_result.processing or 0,
        other=status_counts_result.other or 0,
    )

    # Query for the 5 most recent jobs
    recent_jobs_query = apply_owner_filter(db.query(ConversionJob).order_by(ConversionJob.created_at.desc())).limit(5).all()

    # Assemble the final response object
    return DashboardStats(
        jobs_today=jobs_today,
        jobs_this_week=jobs_this_week,
        status_counts=status_counts,
        recent_jobs=[RecentJob.from_orm(job) for job in recent_jobs_query],
    )
