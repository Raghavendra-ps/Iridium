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
    List the ERPNext link for the current user's organization.
    Returns a list of 0 or 1 item. Managers must belong to an organization.
    """
    if current_user.organization_id is None:
        return []
    links = organization_service.get_linked_organizations_for_org(
        db=db, org_id=current_user.organization_id
    )
    # Return as list of LinkedOrganization (schema expects instance_name from ORM property)
    return links


@router.post("/", response_model=org_schemas.LinkedOrganization, status_code=status.HTTP_201_CREATED)
def create_or_update_my_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_in: ERPNextLinkCreate,
):
    """
    Create or update the ERPNext link for the current user's organization.
    Manager (or superadmin) only; uses current_user.organization_id.
    """
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not assigned to an organization. Contact an administrator.",
        )
    org = organization_service.get_organization_by_id(db=db, org_id=current_user.organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )
    organization_service.link_erpnext_to_organization(
        db=db, org_id=current_user.organization_id, link_in=link_in
    )
    # Reload the link with organization for instance_name
    links = organization_service.get_linked_organizations_for_org(
        db=db, org_id=current_user.organization_id
    )
    if links:
        return links[0]
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Link was not created.",
    )


@router.delete("/{link_id}", response_model=org_schemas.LinkedOrganization)
def delete_my_linked_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_manager_user),
    link_id: int,
):
    """
    Delete the ERPNext link for the current user's organization.
    Only allowed if the link belongs to the user's organization.
    """
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is not assigned to an organization.",
        )
    return organization_service.delete_linked_organization(
        db=db, link_id=link_id, org_id=current_user.organization_id
    )
