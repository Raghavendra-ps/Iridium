from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.db.models import Organization, LinkedOrganization
from app.schemas.organization import OrganizationCreate, ERPNextLinkCreate

def get_organization_by_id(db: Session, org_id: int) -> Optional[Organization]:
    """Retrieves a single organization by its ID."""
    return db.query(Organization).filter(Organization.id == org_id).first()

def get_all_organizations(db: Session) -> List[Organization]:
    """Retrieves all organizations, intended for superadmin use."""
    return db.query(Organization).order_by(Organization.name).options(
        joinedload(Organization.erpnext_link) # Eagerly load the link
    ).all()

def create_organization(db: Session, *, org_in: OrganizationCreate) -> Organization:
    """Creates a new organization."""
    existing_org = db.query(Organization).filter(Organization.name == org_in.name).first()
    if existing_org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An organization with this name already exists.")
    
    db_org = Organization(name=org_in.name)
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org

def link_erpnext_to_organization(db: Session, *, org_id: int, link_in: ERPNextLinkCreate) -> Organization:
    """Creates or updates an ERPNext link for a specific organization."""
    db_org = get_organization_by_id(db, org_id)
    if not db_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    
    # If a link already exists, update it. Otherwise, create a new one.
    if db_org.erpnext_link:
        db_org.erpnext_link.erpnext_url = str(link_in.erpnext_url)
        db_org.erpnext_link.api_key = link_in.api_key
        db_org.erpnext_link.api_secret = link_in.api_secret
    else:
        db_link = LinkedOrganization(
            organization_id=org_id,
            erpnext_url=str(link_in.erpnext_url),
            api_key=link_in.api_key,
            api_secret=link_in.api_secret
        )
        db.add(db_link)
    
    db.commit()
    db.refresh(db_org)
    return db_org

def delete_organization(db: Session, *, org_id: int) -> Organization:
    """Deletes an organization."""
    db_org = get_organization_by_id(db, org_id)
    if not db_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    
    # The ForeignKey constraints with ondelete="SET NULL" will handle unlinking jobs.
    # The cascade="all, delete-orphan" will handle deleting users, employees, and links.
    db.delete(db_org)
    db.commit()
    return db_org