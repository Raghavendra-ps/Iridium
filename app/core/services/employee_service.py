import asyncio
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.db.models import Employee, LinkedOrganization, Organization
from app.schemas.employee import EmployeeCreate, EmployeeUpdate


def get_employees_by_org(db: Session, *, org_id: int) -> List[Employee]:
    """Retrieves all employees for a specific organization (internal only)."""
    return db.query(Employee).filter(Employee.organization_id == org_id).order_by(Employee.employee_name).all()


def get_employees_for_org_any_source(
    db: Session, *, org_id: int
) -> tuple[List[Dict[str, Any]], bool]:
    """
    Returns (list of { employee_code, employee_name }, is_external).
    For internal orgs: from Employee table.
    For external orgs: fetches from ERPNext via LinkedOrganization; employees are immutable.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return [], False
    source = getattr(org, "source", "internal") or "internal"
    if source == "internal":
        employees = get_employees_by_org(db, org_id=org_id)
        return [
            {"employee_code": e.employee_code, "employee_name": e.employee_name}
            for e in employees
        ], False
    # External: fetch from ERPNext
    link = (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.organization_id == org_id)
        .first()
    )
    if not link:
        return [], True
    from app.infrastructure.erpnext_client import ERPNextClient
    client = ERPNextClient(link.erpnext_url, link.api_key, link.api_secret)
    try:
        raw = asyncio.run(client.get_all_employees(force_refresh=True))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch employees from ERPNext: {str(e)}",
        )
    out = []
    for row in raw:
        code = row.get("employee_number") or row.get("name") or ""
        name = row.get("employee_name") or str(code)
        out.append({"employee_code": str(code), "employee_name": str(name)})
    return out, True

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