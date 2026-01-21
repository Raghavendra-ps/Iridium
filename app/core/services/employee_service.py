from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.db.models import Employee, Organization
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

def get_employees_by_org(db: Session, *, org_id: int) -> List[Employee]:
    """Retrieves all employees for a specific organization."""
    return db.query(Employee).filter(Employee.organization_id == org_id).order_by(Employee.employee_name).all()

def create_employee(db: Session, *, org_id: int, employee_in: EmployeeCreate) -> Employee:
    """Creates a new manual employee record for an organization."""
    db_org = db.query(Organization).filter(Organization.id == org_id).first()
    if not db_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    
    db_employee = Employee(**employee_in.dict(), organization_id=org_id)
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def update_employee(db: Session, *, employee_id: int, employee_in: EmployeeUpdate) -> Employee:
    """Updates an employee's details."""
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")
    
    update_data = employee_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_employee, field, value)
        
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def delete_employee(db: Session, *, employee_id: int) -> Employee:
    """Deletes an employee."""
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")
    
    db.delete(db_employee)
    db.commit()
    return db_employee