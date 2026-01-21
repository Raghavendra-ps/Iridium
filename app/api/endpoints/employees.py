from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.api import dependencies
from app.db.models import User
from app.db.session import get_db
from app.schemas import employee as employee_schemas
from app.core.services import employee_service

router = APIRouter()

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

@router.get("/", response_model=List[employee_schemas.Employee])
def list_employees(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
):
    """
    List all manual employees for the current user's organization.
    (Manager or above required)
    """
    return employee_service.get_employees_by_org(db=db, org_id=current_user.organization_id)

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