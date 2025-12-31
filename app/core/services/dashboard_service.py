# Iridium-main/app/core/services/dashboard_service.py

from datetime import datetime, timedelta

from app.api.schemas.dashboard import DashboardStats, JobStatusCounts, RecentJob
from app.db.models import ConversionJob
from sqlalchemy import case, func
from sqlalchemy.orm import Session


def get_dashboard_stats(*, db: Session, owner_id: int) -> DashboardStats:
    """
    Retrieves and aggregates key performance indicators for the user's dashboard.
    """
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=now.weekday())

    # Query for jobs created today and this week
    jobs_today = (
        db.query(ConversionJob)
        .filter(
            ConversionJob.owner_id == owner_id, ConversionJob.created_at >= today_start
        )
        .count()
    )

    jobs_this_week = (
        db.query(ConversionJob)
        .filter(
            ConversionJob.owner_id == owner_id, ConversionJob.created_at >= week_start
        )
        .count()
    )

    # --- START OF FIX ---
    # The previous query had an unmatched parenthesis.
    # This has been rewritten using func.sum() for better clarity and robustness.
    # This pattern sums up '1' for each row that matches the condition.
    status_counts_query = (
        db.query(
            func.sum(
                case((ConversionJob.status == "AWAITING_VALIDATION", 1), else_=0)
            ).label("awaiting_validation"),
            func.sum(case((ConversionJob.status == "COMPLETED", 1), else_=0)).label(
                "completed"
            ),
            func.sum(
                case((ConversionJob.status == "SUBMISSION_FAILED", 1), else_=0)
            ).label("submission_failed"),
            func.sum(
                case(
                    (
                        ConversionJob.status.in_(
                            [
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
        .filter(ConversionJob.owner_id == owner_id)
        .one()
    )
    # --- END OF FIX ---

    status_counts = JobStatusCounts(
        awaiting_validation=status_counts_query.awaiting_validation or 0,
        completed=status_counts_query.completed or 0,
        submission_failed=status_counts_query.submission_failed or 0,
        processing=status_counts_query.processing or 0,
        other=status_counts_query.other or 0,
    )

    # Query for the 5 most recent jobs
    recent_jobs_query = (
        db.query(ConversionJob)
        .filter(ConversionJob.owner_id == owner_id)
        .order_by(ConversionJob.created_at.desc())
        .limit(5)
        .all()
    )

    # Assemble the final response object
    return DashboardStats(
        jobs_today=jobs_today,
        jobs_this_week=jobs_this_week,
        status_counts=status_counts,
        recent_jobs=[RecentJob.from_orm(job) for job in recent_jobs_query],
    )
