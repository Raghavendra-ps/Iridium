import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import job as job_schemas
from app.core.services import analysis_service, job_service
from app.db.models import LinkedOrganization, User
from app.db.session import get_db
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient
from app.models.conversions import ConversionJob

router = APIRouter()
UPLOAD_DIR = Path("/app/uploads")


class JobDataSubmission(BaseModel):
    data: List[Dict[str, Any]]


class EmployeeMappingSubmission(BaseModel):
    job_id: int
    employee_map: Dict[str, str]


class JobStatusResponse(job_schemas.Job):
    attendance_year: Optional[int] = None
    attendance_month: Optional[int] = None


@router.get("/", response_model=list[dict])
def list_jobs(
    *, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(dependencies.get_current_active_user)
):
    """
    Returns filtered data for the Home Dashboard:
    - SuperAdmin: Everything from all users.
    - Manager: Their own conversion jobs.
    - Client: Their own saved sheets/docs.
    """
    query = db.query(ConversionJob)
    
    if current_user.role != 'superadmin':
        # Filter by owner for everyone except SuperAdmins
        query = query.filter(ConversionJob.owner_id == current_user.id)
    
    jobs = query.order_by(ConversionJob.created_at.desc()).all()
    
    return [{
        "id": job.id,
        "original_filename": job.original_filename,
        "target_doctype": job.target_doctype,
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M"),
        "status": job.status,
        # Only show the owner email to superadmins
        "owner_email": job.owner.email if current_user.role == 'superadmin' else None
    } for job in jobs]

@router.post("/upload-for-analysis")
def upload_for_analysis(
    *,
    db: Session = Depends(get_db),
    # --- START OF FIX: Use the correct dependency name ---
    current_user: User = Depends(dependencies.get_current_internal_user),
    # --- END OF FIX ---
    file: UploadFile = File(...),
):
    UPLOAD_DIR.mkdir(exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{Path(file.filename).suffix}"
    destination_path = UPLOAD_DIR / unique_filename
    try:
        with open(destination_path, "wb") as buffer: buffer.write(file.file.read())
        df = pd.read_excel(destination_path, header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read or save file: {e}")
    
    detected_columns, suggestions, preview_data = analysis_service.analyze_file_structure(df)
    job = job_service.create_job(db=db, owner_id=current_user.id, original_filename=file.filename, storage_filename=unique_filename, target_doctype="attendance")
    job.status = "ANALYZING"; db.commit()
    return {"job_id": job.id, "detected_columns": detected_columns, "suggestions": suggestions, "preview_data": preview_data}


@router.post("/process")
def process_file_with_config(
    *,
    db: Session = Depends(get_db),
    # --- START OF FIX: Use the correct dependency name ---
    current_user: User = Depends(dependencies.get_current_internal_user),
    # --- END OF FIX ---
    job_id: int = Form(...),
    target_org_id: int = Form(...),
    attendance_year: int = Form(...),
    attendance_month: int = Form(...),
    parsing_config: str = Form(...),
    mapping_profile_id: Optional[int] = Form(None),
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or job.status != "ANALYZING":
        raise HTTPException(status_code=404, detail="Job not found or not in correct state.")
    try:
        job.target_org_id, job.attendance_year, job.attendance_month, job.parsing_config, job.mapping_profile_id, job.status = target_org_id, attendance_year, attendance_month, json.loads(parsing_config), mapping_profile_id, "PENDING"
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving job config: {e}")
    
    celery.send_task("app.infrastructure.tasks.process_file_task", args=[job.id])
    return {"job_id": job.id, "message": "Job queued for processing."}


@router.get("/{job_id}/employee-map-preview")
async def get_employee_map_preview(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user), # Any active user can see the map preview for their own job
    job_id: int,
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.processed_data_path or not Path(job.processed_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed job data not found.")
    org = db.query(LinkedOrganization).filter(LinkedOrganization.id == job.target_org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Target organization not found.")
    with open(job.processed_data_path, "r") as f: processed_data = json.load(f)
    extracted_employees = {rec.get("employee"): rec.get("employee_name", rec.get("employee")) for rec in processed_data if rec.get("employee")}
    try:
        erp_client = ERPNextClient(base_url=org.erpnext_url, api_key=org.api_key, api_secret=org.api_secret)
        erp_employees = await erp_client.get_all_employees()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not fetch employees from ERPNext: {e}")
    suggestions, unmapped = {}, list(erp_employees)
    for code, name in extracted_employees.items():
        match = next((emp for emp in unmapped if emp.get("company_employee_id") == code), None) or \
                next((emp for emp in unmapped if emp.get("employee_name", "").lower() == name.lower()), None)
        if match:
            suggestions[code] = match["name"]
            unmapped.remove(match)
    return {"extracted_employees": [{"code": c, "name": n} for c, n in extracted_employees.items()], "erp_employees": erp_employees, "suggested_map": suggestions}


@router.post("/submit-with-mapping", status_code=status.HTTP_202_ACCEPTED)
def submit_with_mapping(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), submission: EmployeeMappingSubmission):
    job = job_service.get_job_by_id(db=db, job_id=submission.job_id, owner_id=current_user.id)
    if not job or job.status not in ["AWAITING_VALIDATION", "SUBMISSION_FAILED"]:
        raise HTTPException(status_code=400, detail="Job is not in a submittable state.")
    job.status = "PENDING_SUBMISSION"; db.commit()
    celery.send_task("app.infrastructure.tasks.submit_to_erpnext_task", args=[job.id, submission.employee_map])
    return {"message": "Job has been queued for final submission."}


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/data/raw")
def get_job_raw_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.raw_data_path or not Path(job.raw_data_path).exists():
        raise HTTPException(status_code=404, detail="Raw data not found.")
    return FileResponse(job.raw_data_path, media_type="application/json")


@router.get("/{job_id}/data/processed")
def get_job_processed_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.processed_data_path or not Path(job.processed_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed data not found.")
    return FileResponse(job.processed_data_path, media_type="application/json")


@router.put("/{job_id}/data/processed", status_code=status.HTTP_200_OK)
def save_processed_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int, submission_data: JobDataSubmission):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    if not job.processed_data_path: raise HTTPException(status_code=404, detail="Processed data path not found.")
    validated_data_path = Path(job.processed_data_path)
    try:
        with open(validated_data_path, "w", encoding="utf-8") as f: json.dump(submission_data.data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save edited data: {e}")
    return {"message": "Edits saved successfully."}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    try:
        if job.storage_filename and (original_file := UPLOAD_DIR / job.storage_filename).exists(): original_file.unlink()
        if job.raw_data_path and (raw_file := Path(job.raw_data_path)).exists(): raw_file.unlink()
        if job.processed_data_path and (processed_file := Path(job.processed_data_path)).exists(): processed_file.unlink()
    except Exception as e:
        print(f"Error deleting files for job {job_id}: {e}")
    job_service.delete_job_by_id(db=db, job_id=job_id)
    return None