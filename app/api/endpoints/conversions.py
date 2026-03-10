import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session, joinedload

from app.api import dependencies
from app.api.schemas import job as job_schemas
from app.core.services import analysis_service, job_service
from app.db.models import ConversionJob, LinkedOrganization, Organization, User
from app.db.session import get_db
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

router = APIRouter()
logger = logging.getLogger(__name__)
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
    
    if current_user.role not in ['superadmin', 'manager']:
        # Filter by owner for everyone except SuperAdmins and Managers
        query = query.filter(ConversionJob.owner_id == current_user.id)
        # For Clients, also ensure they only see jobs for their org (double check)
        if current_user.role == 'client' and current_user.organization_id:
             query = query.filter(ConversionJob.target_org_id == current_user.organization_id)
    
    # Filter out initial/transient statuses as per user request to only see "submitted/saved" records
    # We keep 'AWAITING_VALIDATION' because the user needs to see it to take action.
    # We filter out: UPLOADED, ANALYZING, PENDING (processing)
    query = query.filter(ConversionJob.status.notin_(['UPLOADED', 'ANALYZING', 'PENDING']))
    
    # Exclude archived jobs from the main list
    query = query.filter(ConversionJob.is_archived == False)
    
    jobs = query.order_by(ConversionJob.created_at.desc()).all()
    
    return [{
        "id": job.id,
        "original_filename": job.original_filename,
        "target_doctype": job.target_doctype,
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M"),
        "status": job.status,
        "error_log": job.error_log,
        # Only show the owner email to superadmins
        "owner_email": job.owner.email if current_user.role == 'superadmin' else None
    } for job in jobs]


@router.get("/history", response_model=list[dict])
def list_archived_jobs(
    *, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(dependencies.get_current_manager_user)
):
    """
    Returns archived jobs for History view.
    - SuperAdmin: All archived jobs.
    - Manager: Their own archived jobs.
    """
    query = db.query(ConversionJob).filter(ConversionJob.is_archived == True)
    
    if current_user.role != 'superadmin':
        query = query.filter(ConversionJob.owner_id == current_user.id)
    
    jobs = query.order_by(ConversionJob.created_at.desc()).all()
    
    return [{
        "id": job.id,
        "original_filename": job.original_filename,
        "target_doctype": job.target_doctype,
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M"),
        "completed_at": job.completed_at.strftime("%Y-%m-%d %H:%M") if job.completed_at else None,
        "status": job.status,
        "owner_email": job.owner.email if current_user.role == 'superadmin' else None
    } for job in jobs]

@router.post("/upload-for-analysis")
def upload_for_analysis(
    *,
    db: Session = Depends(get_db),
    # --- START OF FIX: Use the correct dependency name ---
    current_user: User = Depends(dependencies.get_current_active_user),
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
    current_user: User = Depends(dependencies.get_current_active_user),
    # --- END OF FIX ---
    job_id: int = Form(...),
    target_org_id: int = Form(...),
    attendance_year: int = Form(...),
    attendance_month: int = Form(...),
    parsing_config: str = Form(...),
    mapping_profile_id: Optional[int] = Form(None),
):
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
        
        # Enforce target organization for Client role
        if current_user.role == 'client' and str(target_org_id) != str(current_user.organization_id):
             raise HTTPException(status_code=403, detail="You can only process files for your own organization.")
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
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.processed_data_path or not Path(job.processed_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed job data not found.")
    
    # Query Organization and joinload the erpnext_link to get the ERPNext URL
    org = db.query(Organization).options(joinedload(Organization.erpnext_link)).filter(Organization.id == job.target_org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Target organization not found.")
    if not org.erpnext_link: raise HTTPException(status_code=404, detail="Target organization is not linked to ERPNext.")
    
    # DEBUG: Log organization details
    logger.info(f"Job target_org_id: {job.target_org_id}")
    logger.info(f"Using ERPNext URL: {org.erpnext_link.erpnext_url}")
    logger.info(f"Organization name: {org.name}")
    
    with open(job.processed_data_path, "r") as f: processed_data = json.load(f)
    extracted_employees = {rec.get("employee"): rec.get("employee_name", rec.get("employee")) for rec in processed_data if rec.get("employee")}
    try:
        erp_client = ERPNextClient(base_url=org.erpnext_link.erpnext_url, api_key=org.erpnext_link.api_key, api_secret=org.erpnext_link.api_secret)
        erp_employees = await erp_client.get_all_employees()
        
        # DEBUG: Log what we're getting from ERPNext
        logger.info(f"ERPNext employees received: {len(erp_employees)}")
        if erp_employees:
            logger.info(f"Sample ERPNext employee keys: {list(erp_employees[0].keys())}")
            logger.info(f"Sample ERPNext employee: {erp_employees[0]}")
        
        # DEBUG: Log extracted employees from file
        logger.info(f"Extracted employees from file: {len(extracted_employees)}")
        logger.info(f"Sample extracted employee: {list(extracted_employees.items())[:3]}")
        
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not fetch employees from ERPNext: {e}")
    # Build suggestions using EXACT MATCHING ONLY (no fuzzy)
    suggestions = {}
    
    # Helper: Normalize text for comparison (case-insensitive)
    def normalize(s: str) -> str:
        if not s:
            return ""
        # Lowercase and remove all special characters/spaces
        return ''.join(c.lower() for c in str(s) if c.isalnum()).strip()
    
    # Prepare ERPNext employee lookup data
    erp_lookup = {}
    for emp in erp_employees:
        emp_id = emp.get("company_employee_id") or emp.get("employee_number") or ""
        emp_name = emp.get("employee_name") or ""
        # Store normalized versions for matching
        erp_lookup[emp["name"]] = {
            "name": emp["name"],
            "employee_id_norm": normalize(emp_id),
            "employee_name_norm": normalize(emp_name),
            "employee_id_raw": emp_id,
            "employee_name_raw": emp_name
        }
    
    # Track already matched ERPNext employee names
    matched_erp_names = set()
    
    # Match each extracted employee
    for code, name in extracted_employees.items():
        code_norm = normalize(code)
        name_norm = normalize(name)
        
        match = None
        method = ""
        
        if not code_norm and not name_norm:
            continue
        
        # Strategy 1: Exact match on employee ID (case-insensitive, no special chars)
        if code_norm:
            for emp_name, emp_data in erp_lookup.items():
                if emp_name in matched_erp_names:
                    continue  # Already matched to another employee
                if code_norm == emp_data["employee_id_norm"]:
                    match = emp_data
                    method = "exact_id"
                    break
        
        # Strategy 2: Exact match on employee name (case-insensitive, no special chars)
        if not match and name_norm:
            for emp_name, emp_data in erp_lookup.items():
                if emp_name in matched_erp_names:
                    continue  # Already matched to another employee
                if name_norm == emp_data["employee_name_norm"]:
                    match = emp_data
                    method = "exact_name"
                    break
        
        if match:
            suggestions[code] = {
                "erp_name": match["name"],
                "confidence": 100 if method == "exact_id" else 90,
                "method": method
            }
            matched_erp_names.add(match["name"])
    
    # Convert suggestions to simple format for frontend
    simple_suggestions = {code: val["erp_name"] if isinstance(val, dict) else val 
                         for code, val in suggestions.items()}
    
    # Also include confidence info in response
    return {
        "extracted_employees": [{"code": c, "name": n} for c, n in extracted_employees.items()], 
        "erp_employees": erp_employees, 
        "suggested_map": simple_suggestions,
        "match_confidence": {code: val["confidence"] if isinstance(val, dict) else 100 
                           for code, val in suggestions.items()}
    }


@router.post("/submit-with-mapping", status_code=status.HTTP_202_ACCEPTED)
def submit_with_mapping(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), submission: EmployeeMappingSubmission):
    print(f"DEBUG: submit_with_mapping called by user {current_user.id} ({current_user.email}) for job {submission.job_id}")
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=submission.job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=submission.job_id, owner_id=current_user.id)
    
    if not job:
        print(f"DEBUG: Job {submission.job_id} not found for user {current_user.id}")
        raise HTTPException(status_code=400, detail="Job not found or access denied.")
        
    print(f"DEBUG: Job found. Status: {job.status}")
    
    if job.status not in ["AWAITING_VALIDATION", "SUBMISSION_FAILED"]:
        print(f"DEBUG: Invalid job status: {job.status}")
        raise HTTPException(status_code=400, detail=f"Job is not in a submittable state (Current: {job.status}).")
        
    job.status = "PENDING_SUBMISSION"; db.commit()
    celery.send_task("app.infrastructure.tasks.submit_to_erpnext_task", args=[job.id, submission.employee_map])
    return {"message": "Job has been queued for final submission."}


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    print(f"DEBUG: get_job_status checked by User {current_user.id} ({current_user.email}) Role: {current_user.role} for Job {job_id}")
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
        print(f"DEBUG: Global fetch result: {job}")
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
        print(f"DEBUG: Owner-scoped fetch result: {job}")
    if not job: 
        print(f"DEBUG: Job {job_id} not found.")
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/data/raw")
def get_job_raw_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.raw_data_path or not Path(job.raw_data_path).exists():
        raise HTTPException(status_code=404, detail="Raw data not found.")
    return FileResponse(job.raw_data_path, media_type="application/json")


@router.get("/{job_id}/data/processed")
def get_job_processed_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int):
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.processed_data_path or not Path(job.processed_data_path).exists():
        raise HTTPException(status_code=404, detail="Processed data not found.")
    return FileResponse(job.processed_data_path, media_type="application/json")


@router.put("/{job_id}/data/processed", status_code=status.HTTP_200_OK)
def save_processed_data(*, db: Session = Depends(get_db), current_user: User = Depends(dependencies.get_current_user), job_id: int, submission_data: JobDataSubmission):
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
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
def archive_job(
    *, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(dependencies.get_current_manager_user), 
    job_id: int
):
    """
    Archives a job (soft delete) instead of permanently deleting it.
    Only Superadmins and Managers can archive jobs.
    """
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        # Should normally not happen given dependency, but specific client route might exist in future
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)

    if not job: 
        raise HTTPException(status_code=404, detail="Job not found")
    
    # If already archived, perform hard delete (optional, or just do nothing)
    # For now, let's keep it simple: Archive it.
    job.is_archived = True
    db.commit()
    return None


@router.post("/{job_id}/restore", status_code=status.HTTP_200_OK)
def restore_job(
    *, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(dependencies.get_current_manager_user), 
    job_id: int
):
    """
    Restores an archived job to the main dashboard.
    """
    if current_user.role in ['superadmin', 'manager']:
        job = job_service.get_job_by_id_global(db=db, job_id=job_id)
    else:
        job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)

    if not job: 
        raise HTTPException(status_code=404, detail="Job not found")
        
    job.is_archived = False
    db.commit()
    return {"message": "Job restored successfully."}