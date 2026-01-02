from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from app.db.models import ConversionJob


def get_jobs_by_owner(db: Session, *, owner_id: int) -> list[ConversionJob]:
    """
    Retrieves all conversion jobs for a specific user.
    """
    return (
        db.query(ConversionJob)
        .filter(ConversionJob.owner_id == owner_id)
        .order_by(ConversionJob.created_at.desc())
        .all()
    )


def get_job_by_id(db: Session, *, job_id: int, owner_id: int) -> ConversionJob | None:
    """
    Retrieves a single job by its ID, ensuring it belongs to the correct owner.
    """
    return (
        db.query(ConversionJob)
        .filter(ConversionJob.id == job_id, ConversionJob.owner_id == owner_id)
        .first()
    )


def delete_job_by_id(db: Session, *, job_id: int) -> None:
    """Deletes a job from the database by its ID."""
    try:
        # We find the job first to ensure we can delete it, then proceed.
        job_to_delete = db.query(ConversionJob).filter(ConversionJob.id == job_id).one()
        db.delete(job_to_delete)
        db.commit()
    except NoResultFound:
        # If the job is already gone, our goal is met. Do nothing.
        pass


def create_job(
    db: Session,
    *,
    owner_id: int,
    original_filename: str,
    storage_filename: str,
    target_doctype: str,
    target_org_id: Optional[int] = None,  # Made optional for initial creation
) -> ConversionJob:
    """
    Creates a new, initial conversion job record in the database.
    More details (like parsing config) will be added in a subsequent step.
    """
    db_job = ConversionJob(
        owner_id=owner_id,
        original_filename=original_filename,
        storage_filename=storage_filename,
        target_doctype=target_doctype,
        target_org_id=target_org_id,
        # Status is simply 'UPLOADED' initially
        status="UPLOADED",
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job
