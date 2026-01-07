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
from app.infrastructure.tasks import read_tabular_file

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
    current_user: User = Depends(dependencies.get_current_user),
):
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


@router.post("/upload-for-analysis")
def upload_for_analysis(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    file: UploadFile = File(...),
):
    UPLOAD_DIR.mkdir(exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{Path(file.filename).suffix}"
    destination_path = UPLOAD_DIR / unique_filename
    try:
        with open(destination_path, "wb") as buffer:
            buffer.write(file.file.read())
        df = pd.read_excel(destination_path, header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read or save file: {e}")
    detected_columns, suggestions, preview_data = (
        analysis_service.analyze_file_structure(df)
    )
    job = job_service.create_job(
        db=db,
        owner_id=current_user.id,
        original_filename=file.filename,
        storage_filename=unique_filename,
        target_doctype="attendance",
    )
    job.status = "ANALYZING"
    db.commit()
    return {
        "job_id": job.id,
        "detected_columns": detected_columns,
        "suggestions": suggestions,
        "preview_data": preview_data,
    }


@router.post("/process")
def process_file_with_config(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int = Form(...),
    target_org_id: int = Form(...),
    attendance_year: int = Form(...),
    attendance_month: int = Form(...),
    parsing_config: str = Form(...),
    mapping_profile_id: Optional[int] = Form(None),
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or job.status != "ANALYZING":
        raise HTTPException(
            status_code=404, detail="Job not found or not in correct state."
        )
    try:
        (
            job.target_org_id,
            job.attendance_year,
            job.attendance_month,
            job.parsing_config,
            job.mapping_profile_id,
            job.status,
        ) = (
            target_org_id,
            attendance_year,
            attendance_month,
            json.loads(parsing_config),
            mapping_profile_id,
            "PENDING",
        )
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
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if (
        not job
        or not job.processed_data_path
        or not Path(job.processed_data_path).exists()
    ):
        raise HTTPException(status_code=404, detail="Processed job data not found.")
    org = (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.id == job.target_org_id)
        .first()
    )
    if not org:
        raise HTTPException(status_code=404, detail="Target organization not found.")
    with open(job.processed_data_path, "r") as f:
        processed_data = json.load(f)
    extracted_employees = {
        rec.get("employee"): rec.get("employee_name", rec.get("employee"))
        for rec in processed_data
        if rec.get("employee")
    }
    try:
        erp_client = ERPNextClient(
            base_url=org.erpnext_url, api_key=org.api_key, api_secret=org.api_secret
        )
        erp_employees = await erp_client.get_all_employees()
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Could not fetch employees from ERPNext: {e}"
        )
    suggestions, unmapped = {}, list(erp_employees)
    for code, name in extracted_employees.items():
        match = next(
            (emp for emp in unmapped if emp.get("company_employee_id") == code), None
        ) or next(
            (
                emp
                for emp in unmapped
                if emp.get("employee_name", "").lower() == name.lower()
            ),
            None,
        )
        if match:
            suggestions[code] = match["name"]
            unmapped.remove(match)
    return {
        "extracted_employees": [
            {"code": c, "name": n} for c, n in extracted_employees.items()
        ],
        "erp_employees": erp_employees,
        "suggested_map": suggestions,
    }


@router.get("/{job_id}/erpnext-employees")
async def get_erpnext_employees_for_mapping(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """
    Fetch both extracted and ERPNext employees for mapping UI.
    Includes debug logging and connection testing.
    """
    print("\n" + "=" * 80)
    print(f"🔍 EMPLOYEE MAPPING - Starting fetch for Job ID: {job_id}")
    print("=" * 80)

    # Get job
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        print("❌ ERROR: Job not found")
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.processed_data_path or not Path(job.processed_data_path).exists():
        print(f"❌ ERROR: Processed data path not found: {job.processed_data_path}")
        raise HTTPException(status_code=404, detail="Processed job data not found")

    print(f"✅ Job found: {job.original_filename}")
    print(f"📁 Processed data path: {job.processed_data_path}")

    # Get target organization
    org = (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.id == job.target_org_id)
        .first()
    )

    if not org:
        print(f"❌ ERROR: Organization not found (ID: {job.target_org_id})")
        raise HTTPException(status_code=404, detail="Target organization not found")

    print(f"✅ Organization found: ID {org.id}")
    print(f"🌐 ERPNext URL: {org.erpnext_url}")
    print(f"🔑 API Key: {org.api_key[:15]}...{org.api_key[-5:]}")
    print(f"🔒 API Secret: {org.api_secret[:15]}...{org.api_secret[-5:]}")

    # Load extracted employees from processed data
    print("\n📊 Loading extracted employees from processed data...")
    try:
        with open(job.processed_data_path, "r", encoding="utf-8") as f:
            processed_data = json.load(f)

        extracted = {}
        for rec in processed_data:
            emp_code = rec.get("employee")
            if emp_code and emp_code not in extracted:
                extracted[emp_code] = rec.get("employee_name", emp_code)

        print(f"✅ Found {len(extracted)} unique employees in processed data")
        print(f"📋 Sample codes: {list(extracted.keys())[:5]}")

    except Exception as e:
        print(f"❌ ERROR loading processed data: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to load processed data: {str(e)}"
        )

    # Create ERPNext client
    print("\n🔗 Creating ERPNext client...")
    erp_client = ERPNextClient(
        base_url=org.erpnext_url, api_key=org.api_key, api_secret=org.api_secret
    )

    # Test connection first
    print("🧪 Testing ERPNext connection...")
    try:
        connection_test = await erp_client.check_connection()
        print(f"Connection test result: {connection_test}")

        if connection_test["status"] != "online":
            print(f"❌ Connection test failed: {connection_test['details']}")
            raise HTTPException(
                status_code=503,
                detail=f"ERPNext connection failed: {connection_test['details']}",
            )

        print("✅ ERPNext connection successful!")

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Connection test error: {str(e)}")
        raise HTTPException(
            status_code=503, detail=f"ERPNext connection error: {str(e)}"
        )

    # Fetch ERPNext employees
    print("\n👥 Fetching employees from ERPNext...")
    try:
        erp_employees = await erp_client.get_all_employees()
        print(f"✅ Successfully fetched {len(erp_employees)} employees from ERPNext")

        if len(erp_employees) > 0:
            print(f"📋 Sample ERPNext employee: {erp_employees[0]}")
        else:
            print("⚠️ WARNING: No employees found in ERPNext!")

    except Exception as e:
        print(f"❌ ERROR fetching ERPNext employees: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=503, detail=f"Failed to fetch ERPNext employees: {str(e)}"
        )

    # Prepare response
    response_data = {
        "extracted_employees": [
            {"code": code, "name": name} for code, name in extracted.items()
        ],
        "erpnext_employees": erp_employees,
        "job_id": job_id,
    }

    print("\n✅ SUCCESS - Returning data to frontend")
    print(f"📤 Extracted employees: {len(response_data['extracted_employees'])}")
    print(f"📤 ERPNext employees: {len(response_data['erpnext_employees'])}")
    print("=" * 80 + "\n")

    return response_data


@router.post("/submit-with-mapping", status_code=status.HTTP_202_ACCEPTED)
def submit_with_mapping(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    submission: EmployeeMappingSubmission,
):
    job = job_service.get_job_by_id(
        db=db, job_id=submission.job_id, owner_id=current_user.id
    )
    if not job or job.status not in ["AWAITING_VALIDATION", "SUBMISSION_FAILED"]:
        raise HTTPException(
            status_code=400, detail="Job is not in a submittable state."
        )
    job.status = "PENDING_SUBMISSION"
    db.commit()
    celery.send_task(
        "app.infrastructure.tasks.submit_to_erpnext_task",
        args=[job.id, submission.employee_map],
    )
    return {"message": "Job has been queued for final submission."}


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
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
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job or not job.raw_data_path or not Path(job.raw_data_path).exists():
        raise HTTPException(status_code=404, detail="Raw data not found.")
    return FileResponse(job.raw_data_path, media_type="application/json")


@router.get("/{job_id}/data/processed")
def get_job_processed_data(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if (
        not job
        or not job.processed_data_path
        or not Path(job.processed_data_path).exists()
    ):
        raise HTTPException(status_code=404, detail="Processed data not found.")
    return FileResponse(job.processed_data_path, media_type="application/json")


# --- START OF NEW ENDPOINT ---
@router.put("/{job_id}/data/processed", status_code=status.HTTP_200_OK)
def save_processed_data(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
    submission_data: JobDataSubmission,
):
    """
    Saves the user's edits from the validation grid back to the processed data file.
    This is called before proceeding to the employee mapping step.
    """
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.processed_data_path:
        raise HTTPException(
            status_code=404, detail="Processed data path not found for this job."
        )

    validated_data_path = Path(job.processed_data_path)
    try:
        with open(validated_data_path, "w", encoding="utf-8") as f:
            json.dump(submission_data.data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save edited data: {e}")

    return {"message": "Edits saved successfully."}


# --- END OF NEW ENDPOINT ---


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        if job.storage_filename:
            original_file = UPLOAD_DIR / job.storage_filename
            if original_file.exists():
                original_file.unlink()
        if job.raw_data_path:
            raw_file = Path(job.raw_data_path)
            if raw_file.exists():
                raw_file.unlink()
        if job.processed_data_path:
            processed_file = Path(job.processed_data_path)
            if processed_file.exists():
                processed_file.unlink()
    except Exception as e:
        print(f"Error deleting files for job {job_id}: {e}")
    job_service.delete_job_by_id(db=db, job_id=job_id)
    return None


# Add to conversions.py
@router.get("/{job_id}/test-erpnext-connection")
async def test_erpnext_connection(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    job_id: int,
):
    """Debug endpoint to test ERPNext connection"""
    job = job_service.get_job_by_id(db=db, job_id=job_id, owner_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    org = (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.id == job.target_org_id)
        .first()
    )

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Test connection
    erp_client = ERPNextClient(
        base_url=org.erpnext_url, api_key=org.api_key, api_secret=org.api_secret
    )

    result = await erp_client.check_connection()

    return {
        "erpnext_url": org.erpnext_url,
        "api_key_preview": org.api_key[:10] + "...",
        "connection_test": result,
    }
