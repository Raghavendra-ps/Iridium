import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api import dependencies
from app.db.session import get_db
from app.db.models import User, ConversionJob

router = APIRouter()

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"

class SheetDataSubmission(BaseModel):
    year: int
    month: int
    data: List[Dict[str, Any]]
    target_org_id: Optional[int] = None

@router.post("/save-as-job", status_code=status.HTTP_201_CREATED)
def save_sheet_as_job(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_active_user),
    submission: SheetDataSubmission,
):
    """
    Takes manual grid data from the Sheet Maker and saves it as a 
    pre-processed job so it appears on the dashboard.
    """
    if not submission.data:
        raise HTTPException(status_code=400, detail="No data provided.")

    PROCESSED_DIR.mkdir(exist_ok=True, parents=True)
    job_uuid = uuid.uuid4()
    
    # Transform grid data to flattened records
    records = []
    for row in submission.data:
        emp_code = row.get("Employee Code") or row.get("Emp Code")
        emp_name = row.get("Employee Name") or row.get("Emp Name")
        if not emp_code: continue
        
        for day_key, status_val in row.items():
            # Check if key is a day number (1, 2, 3...)
            if day_key.isdigit() and status_val:
                date_str = f"{submission.year}-{submission.month:02d}-{int(day_key):02d}"
                records.append({
                    "employee": str(emp_code),
                    "employee_name": str(emp_name),
                    "attendance_date": date_str,
                    "status": str(status_val)
                })

    if not records:
        raise HTTPException(status_code=400, detail="No attendance markers found in grid.")

    # Save the flattened JSON to disk
    file_path = PROCESSED_DIR / f"{job_uuid}_processed.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    # Create the job entry
    # Note: We set status to AWAITING_VALIDATION so the user can see it on Home immediately.
    new_job = ConversionJob(
        owner_id=current_user.id,
        target_org_id=submission.target_org_id or current_user.organization_id,
        attendance_year=submission.year,
        attendance_month=submission.month,
        status="AWAITING_VALIDATION", 
        target_doctype="attendance",
        original_filename=f"Manual Entry - {submission.year}/{submission.month:02d}",
        storage_filename=f"{job_uuid}.manual",
        processed_data_path=str(file_path)
    )
    
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    return {"id": new_job.id, "message": "Document saved successfully."}