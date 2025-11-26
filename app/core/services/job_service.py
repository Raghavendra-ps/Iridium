from sqlalchemy.orm import Session

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
    db.query(ConversionJob).filter(ConversionJob.id == job_id).delete()
    db.commit()


def create_job(
    db: Session,
    *,
    owner_id: int,
    original_filename: str,
    storage_filename: str,
    target_doctype: str,
    target_org_id: int,
) -> ConversionJob:
    """Creates a new conversion job record in the database."""
    db_job = ConversionJob(
        owner_id=owner_id,
        original_filename=original_filename,
        storage_filename=storage_filename,
        target_doctype=target_doctype,
        target_org_id=target_org_id,
        status="UPLOADED",  # Initial status
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job
