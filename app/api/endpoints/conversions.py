import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import job as job_schemas
from app.core.services import job_service
from app.db.models import User
from app.db.session import get_db
from app.infrastructure.celery_app import celery

router = APIRouter()
UPLOAD_DIR = Path("/app/uploads")


class JobDataSubmission(BaseModel):
    data: List[Dict[str, Any]]


class JobStatusResponse(job_schemas.Job):
    """Extend the Job schema to include dynamic date info for the UI."""

    attendance_year: Optional[int] = None
    attendance_month: Optional[int] = None


@router.get("/", response_model=list[dict])
def list_jobs(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """List all conversion jobs for the current user."""
    jobs = job_service.get_jobs_by_owner(db, owner_id=current_user.id)
    return [
        {
            "id": job.id,
            "original_filename": job.original_filename,
            "target_doctype": job.target_doctype,
            "created_at": job.created_at.strftime("%Y-%m-%d %H:%M") + " UTC",
            "status": job.status,
        }
        for job in jobs
    ]


@router.post("/upload", response_model=job_schemas.Job)
def upload_file(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    file: UploadFile = File(...),
    target_org_id: int = Form(...),
    doctype: str = Form(...),
    import_template_id: Optional[int] = Form(None),
    mapping_profile_id: Optional[int] = Form(None),
    attendance_year: Optional[int] = Form(None),
    attendance_month: Optional[int] = Form(None),
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
        target_org_id=target_org_id,
        mapping_profile_id=mapping_profile_id,
        import_template_id=import_template_id,
        attendance_year=attendance_year,
        attendance_month=attendance_month,
    )

    celery.send_task("app.infrastructure.tasks.process_file_task", args=[job.id])
    return job


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """Get the current status and details of a specific job."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/data/raw")
def get_job_raw_data(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """Get the raw, unprocessed tabular data extracted from the source file."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.raw_data_path or not Path(job.raw_data_path).exists():
        raise HTTPException(status_code=404, detail="Raw data not found for this job.")
    return FileResponse(job.raw_data_path, media_type="application/json")


@router.get("/{job_id}/data/processed")
def get_job_processed_data(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """Get the final, processed data after parsing rules have been applied."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.processed_data_path or not Path(job.processed_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed data not found.")
    return FileResponse(job.processed_data_path, media_type="application/json")


@router.post("/{job_id}/submit", status_code=status.HTTP_202_ACCEPTED)
def submit_job_for_processing(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
    submission_data: JobDataSubmission,
):
    """
    Receives user-validated data, saves it, and dispatches the ERPNext submission task.
    """
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ["AWAITING_VALIDATION", "SUBMISSION_FAILED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not in a submittable state. Current status: {job.status}",
        )

    # --- START OF FIX ---
    # Check for the correct column: `processed_data_path` instead of `intermediate_data_path`.
    if not job.processed_data_path:
        raise HTTPException(
            status_code=404,
            detail="Processed data path not set. The job may not have been fully processed yet.",
        )

    # Use the correct path to overwrite with the user's validated data.
    validated_data_path = Path(job.processed_data_path)
    # --- END OF FIX ---

    try:
        with open(validated_data_path, "w", encoding="utf-8") as f:
            json.dump(submission_data.data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save validated data: {e}",
        )

    job.status = "PENDING_SUBMISSION"
    db.commit()

    celery.send_task("app.infrastructure.tasks.submit_to_erpnext_task", args=[job.id])

    return JSONResponse(
        content={
            "message": "Job submission accepted and is being processed in the background."
        }
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """Delete a conversion job and its associated files."""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        # Delete original uploaded file
        original_file = UPLOAD_DIR / job.storage_filename
        if original_file.exists():
            original_file.unlink()

        # Delete raw and processed data files
        if job.raw_data_path:
            raw_file = Path(job.raw_data_path)
            if raw_file.exists():
                raw_file.unlink()
        if job.processed_data_path:
            processed_file = Path(job.processed_data_path)
            if processed_file.exists():
                processed_file.unlink()

    except Exception as e:
        # Log this error but don't block the job deletion from the DB
        print(f"Error deleting files for job {job_id}: {e}")

    job_service.delete_job_by_id(db=db, job_id=job_id)

    return None
