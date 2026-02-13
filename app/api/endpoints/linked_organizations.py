"""
Endpoints for managers to manage their own organization's ERPNext link.
Uses current_user.organization_id; requires authenticated user with an organization.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import organization as org_schemas
from app.core.services import organization_service
from app.db.models import User
from app.db.session import get_db
from app.schemas.organization import ERPNextLinkCreate

router = APIRouter()


@router.get("/", response_model=List[org_schemas.LinkedOrganization])
def list_my_linked_organizations(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_active_user),
):
    """
    List ERPNext links.
    Superadmin: lists ALL links.
    Manager/Client: lists only their org's link.
    """
    if current_user.role == "superadmin":
         return organization_service.get_all_linked_organizations(db=db)

    if current_user.organization_id is None:
        return []
    return organization_service.get_linked_organizations_for_org(
        db=db, org_id=current_user.organization_id
    )


@router.post("/", response_model=org_schemas.LinkedOrganization, status_code=status.HTTP_201_CREATED)
def create_or_update_my_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_in: ERPNextLinkCreate,
):
    """
    Create or update ERPNext link.
    Superadmin: Can link any org via link_in.organization_id.
    Manager: Can only link their own organization.
    """
    target_org_id = current_user.organization_id
    
    if current_user.role == "superadmin":
        if link_in.organization_id:
            target_org_id = link_in.organization_id
        elif not target_org_id:
             # If superadmin has no org assigned AND didn't provide one
             raise HTTPException(status_code=400, detail="Organization ID is required for Superadmins without an assigned organization.")
    
    if not target_org_id:
         raise HTTPException(status_code=400, detail="No organization assigned to user.")

    # verify org exists
    org = organization_service.get_organization_by_id(db=db, org_id=target_org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    organization_service.link_erpnext_to_organization(
        db=db, org_id=target_org_id, link_in=link_in
    )
    
    # Return the created/updated link
    links = organization_service.get_linked_organizations_for_org(db=db, org_id=target_org_id)
    return links[0] if links else None


@router.delete("/{link_id}", response_model=org_schemas.LinkedOrganization)
def delete_my_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_id: int,
):
    """
    Delete the ERPNext link.
    Superadmin: Can delete any link.
    Manager: Can only delete their own org's link.
    """
    if current_user.role == "superadmin":
         return organization_service.delete_linked_organization_any(db=db, link_id=link_id)
    
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not assigned to an organization.",
        )
    return organization_service.delete_linked_organization(
        db=db, link_id=link_id, org_id=current_user.organization_id
    )
