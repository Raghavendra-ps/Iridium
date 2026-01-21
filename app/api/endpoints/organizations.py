from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.db.models import User
from app.db.session import get_db
from app.schemas import organization as org_schemas
from app.core.services import organization_service

router = APIRouter()

@router.post("/", response_model=org_schemas.Organization, status_code=status.HTTP_201_CREATED)
def create_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_superadmin_user),
    org_in: org_schemas.OrganizationCreate,
):
    """
    Create a new organization. (Superadmin only)
    """
    return organization_service.create_organization(db=db, org_in=org_in)

@router.get("/", response_model=List[org_schemas.Organization])
def list_organizations(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_superadmin_user),
):
    """
    List all organizations in the system. (Superadmin only)
    """
    return organization_service.get_all_organizations(db=db)

@router.post("/{org_id}/link-erpnext", response_model=org_schemas.Organization)
def link_erpnext(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_superadmin_user),
    org_id: int,
    link_in: org_schemas.ERPNextLinkCreate,
):
    """
    Link or update an ERPNext instance for an organization. (Superadmin only)
    """
    return organization_service.link_erpnext_to_organization(db=db, org_id=org_id, link_in=link_in)

@router.delete("/{org_id}", response_model=org_schemas.Organization)
def delete_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_superadmin_user),
    org_id: int,
):
    """
    Delete an organization and all its associated users, employees, and jobs. (Superadmin only)
    """
    return organization_service.delete_organization(db=db, org_id=org_id)