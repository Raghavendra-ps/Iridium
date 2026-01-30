import json
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import dependencies
from app.db.session import get_db
from app.db.models import User, Employee, ConversionJob

router = APIRouter()

@router.get("/my-records")
def get_my_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_active_user)
):
    """
    Finds the Employee record matching the user's email and pulls 
    their history from all completed jobs in their organisation.
    """
    # 1. Identity Link: Look for an employee entry with this user's email
    emp_record = db.query(Employee).filter(Employee.email == current_user.email).first()
    
    if not emp_record:
        # If the manager hasn't added this email to the Employee Setup yet
        raise HTTPException(
            status_code=404, 
            detail=f"No linked employee record found for {current_user.email}. Please contact your manager."
        )

    # 2. Scope Link: Find all COMPLETED jobs for this organization
    jobs = db.query(ConversionJob).filter(
        ConversionJob.target_org_id == current_user.organization_id,
        ConversionJob.status == "COMPLETED"
    ).order_by(ConversionJob.attendance_year.desc(), ConversionJob.attendance_month.desc()).all()

    attendance_history = []

    # 3. Data Extraction: Scan the JSON files
    for job in jobs:
        if not job.processed_data_path:
            continue
            
        file_path = Path(job.processed_data_path)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    # Filter: Only grab rows belonging to this employee's code
                    my_rows = [r for r in records if r.get('employee') == emp_record.employee_code]
                    
                    if my_rows:
                        attendance_history.append({
                            "year": job.attendance_year,
                            "month": job.attendance_month,
                            "filename": job.original_filename,
                            "days": my_rows
                        })
            except Exception as e:
                print(f"Error reading job {job.id}: {e}")

    return {
        "employee_name": emp_record.employee_name,
        "employee_code": emp_record.employee_code,
        "organisation_id": current_user.organization_id,
        "history": attendance_history
    }