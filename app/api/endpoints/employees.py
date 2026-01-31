from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from app.api import dependencies
from app.db.models import User
from app.db.session import get_db
from app.schemas import employee as employee_schemas
from app.core.services import employee_service
from app.db.models import Employee, User
from pydantic import BaseModel

router = APIRouter()

class EmployeeSync(BaseModel):
    code: str
    name: str
    email: str | None = None

@router.post("/", response_model=employee_schemas.Employee, status_code=status.HTTP_201_CREATED)
def create_employee(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    employee_in: employee_schemas.EmployeeCreate,
):
    """
    Create a new manual employee for the current user's organization.
    (Manager or above required)
    """
    # Managers can only add employees to their own organization
    org_id = current_user.organization_id
    return employee_service.create_employee(db=db, org_id=org_id, employee_in=employee_in)

@router.get("/", response_model=List[dict])
def list_employees(
    org_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_active_user),
):
    """
    List employees for an organization. Internal orgs: from DB (editable).
    External orgs: fetched from ERPNext (immutable). Superadmin can pass any org_id; manager only their org.
    """
    target_id = org_id if org_id is not None else current_user.organization_id
    if not target_id:
        return []
    if current_user.role != "superadmin" and target_id != current_user.organization_id:
        return []
    employees, is_external = employee_service.get_employees_for_org_any_source(db=db, org_id=target_id)
    # Add is_external so frontend can make grid read-only for external orgs
    for e in employees:
        e["is_external"] = is_external
    return employees

@router.put("/{employee_id}", response_model=employee_schemas.Employee)
def update_employee(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    employee_id: int,
    employee_in: employee_schemas.EmployeeUpdate,
):
    """
    Update an employee's details. Ensures the employee belongs to the user's organization.
    (Manager or above required)
    """
    db_employee = db.query(employee_schemas.Employee).filter(employee_schemas.Employee.id == employee_id).first()
    if not db_employee or db_employee.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found in your organization.")
    
    return employee_service.update_employee(db=db, employee_id=employee_id, employee_in=employee_in)

@router.delete("/{employee_id}", response_model=employee_schemas.Employee)
def delete_employee(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    employee_id: int,
):
    """
    Delete an employee. Ensures the employee belongs to the user's organization.
    (Manager or above required)
    """
    db_employee = db.query(employee_schemas.Employee).filter(employee_schemas.Employee.id == employee_id).first()
    if not db_employee or db_employee.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found in your organization.")
        
    return employee_service.delete_employee(db=db, employee_id=employee_id)


@router.post("/sync/{org_id}", status_code=status.HTTP_200_OK)
def sync_org_employees(
    org_id: int,
    employees_in: List[EmployeeSync],
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
):
    """
    Bulk updates the employee roster for an organization (internal only).
    External org employees are immutable; this endpoint returns 403 for external orgs.
    """
    if current_user.role != "superadmin" and current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this organization.")
    from app.db.models import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and (getattr(org, "source", "internal") or "internal") == "external":
        raise HTTPException(
            status_code=403,
            detail="External organization employees are managed in ERPNext and cannot be edited here.",
        )

    # 1. Clear existing roster
    db.query(Employee).filter(Employee.organization_id == org_id).delete()
    
    # 2. Insert new roster from the grid
    for emp in employees_in:
        new_emp = Employee(
            organization_id=org_id,
            employee_code=emp.code,
            employee_name=emp.name,
            email=emp.email
        )
        db.add(new_emp)
    
    db.commit()
    return {"message": f"Successfully synced {len(employees_in)} employees."}