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
def list_linked_organizations(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_active_user),
):
    """
    List ERPNext links (Global Access).
    """
    return organization_service.get_all_linked_organizations(db=db)


@router.post("/", response_model=org_schemas.LinkedOrganization, status_code=status.HTTP_201_CREATED)
def create_or_update_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_in: ERPNextLinkCreate,
):
    """
    Create or update ERPNext link (Global Access).
    """
    target_org_id = None
    
    if link_in.organization_id:
        target_org_id = link_in.organization_id
    elif current_user.organization_id:
        target_org_id = current_user.organization_id
    
    if not target_org_id:
         raise HTTPException(status_code=400, detail="Organization ID is required.")

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
def delete_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_id: int,
):
    """
    Delete the ERPNext link (Global Access).
    """
    return organization_service.delete_linked_organization_any(db=db, link_id=link_id)
