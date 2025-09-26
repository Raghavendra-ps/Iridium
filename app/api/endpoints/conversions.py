import uuid
from pathlib import Path
import json

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import dependencies
from app.db.models import User
from app.db.session import get_db
from app.core.services import job_service
from app.api.schemas import job as job_schemas
from app.infrastructure import tasks

router = APIRouter()
UPLOAD_DIR = Path("/app/uploads")

@router.get("/", response_model=list[dict])
def list_jobs(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user)
):
    """List all conversion jobs for the current user."""
    jobs = job_service.get_jobs_by_owner(db, owner_id=current_user.id)
    return [
        {
            "id": job.id,
            "original_filename": job.original_filename,
            "target_doctype": job.target_doctype,
            "created_at": job.created_at.strftime('%Y-%m-%d %H:%M') + " UTC",
            "status": job.status
        } for job in jobs
    ]

@router.post("/upload", response_model=job_schemas.Job)
def upload_file(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    file: UploadFile = File(...),
    target_org_id: int = Form(...),
    doctype: str = Form(...)
):
    """Upload a file, create a job record, and dispatch a background task."""
    UPLOAD_DIR.mkdir(exist_ok=True)

    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    destination_path = UPLOAD_DIR / unique_filename

    try:
        with open(destination_path, "wb") as buffer:
            buffer.write(file.file.read())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"There was an error saving the file: {e}",
        )

    job = job_service.create_job(
        db=db,
        owner_id=current_user.id,
        original_filename=file.filename,
        storage_filename=unique_filename,
        target_doctype=doctype,
        target_org_id=target_org_id
    )

    tasks.process_file_task.delay(job.id)
    return job

@router.get("/{job_id}/status", response_model=job_schemas.Job)
def get_job_status(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int
):
    """Get the current status and details of a specific job."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/{job_id}/data")
def get_job_data(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int
):
    """Get the processed intermediate JSON data for a job."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.intermediate_data_path or not Path(job.intermediate_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed data not found for this job. It may still be processing or failed.")

    return FileResponse(job.intermediate_data_path, media_type="application/json")

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int
):
    """
    Delete a conversion job and its associated files.
    """
    # First, get the job and verify ownership
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete associated files from the disk
    try:
        # Delete the original uploaded file
        original_file = UPLOAD_DIR / job.storage_filename
        if original_file.exists():
            original_file.unlink()

        # Delete the processed JSON file, if it exists
        if job.intermediate_data_path:
            processed_file = Path(job.intermediate_data_path)
            if processed_file.exists():
                processed_file.unlink()
    except Exception as e:
        # Log this error but don't stop the DB deletion.
        # The job record is the source of truth.
        print(f"Error deleting files for job {job_id}: {e}")

    # Delete the job record from the database
    job_service.delete_job_by_id(db=db, job_id=job_id)

    # A 204 response has no body, so we return None
    return None
