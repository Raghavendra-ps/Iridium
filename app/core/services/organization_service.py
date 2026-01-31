from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.db.models import Organization, LinkedOrganization
from app.schemas.organization import OrganizationCreate, ERPNextLinkCreate, ExternalOrganizationCreate

def get_organization_by_id(db: Session, org_id: int) -> Optional[Organization]:
    """Retrieves a single organization by its ID."""
    return db.query(Organization).filter(Organization.id == org_id).first()

def get_all_organizations(db: Session) -> List[Organization]:
    """Retrieves all organizations, intended for superadmin use."""
    return db.query(Organization).order_by(Organization.name).options(
        joinedload(Organization.erpnext_link)
    ).all()


def get_organizations_for_dropdown(
    db: Session, *, user_organization_id: Optional[int], is_superadmin: bool
) -> List[Dict[str, Any]]:
    """Returns orgs for sheet maker dropdown: superadmin sees all, manager sees only their org."""
    if is_superadmin:
        orgs = db.query(Organization).order_by(Organization.name).all()
    else:
        if not user_organization_id:
            return []
        orgs = db.query(Organization).filter(Organization.id == user_organization_id).all()
    return [
        {"id": o.id, "name": o.name, "source": getattr(o, "source", "internal") or "internal"}
        for o in orgs
    ]


def create_organization(db: Session, *, org_in: OrganizationCreate) -> Organization:
    """Creates a new internal organization."""
    existing_org = db.query(Organization).filter(Organization.name == org_in.name).first()
    if existing_org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An organization with this name already exists.")
    
    db_org = Organization(name=org_in.name, source="internal")
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org


def create_external_organization(db: Session, *, ext_in: ExternalOrganizationCreate) -> Organization:
    """Creates an external organization (ERPNext) and its link in one step."""
    existing_org = db.query(Organization).filter(Organization.name == ext_in.name).first()
    if existing_org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An organization with this name already exists.")
    
    db_org = Organization(name=ext_in.name, source="external")
    db.add(db_org)
    db.flush()  # get db_org.id
    db_link = LinkedOrganization(
        organization_id=db_org.id,
        erpnext_url=str(ext_in.erpnext_url),
        api_key=ext_in.api_key,
        api_secret=ext_in.api_secret,
    )
    db.add(db_link)
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

def get_linked_organizations_for_org(db: Session, *, org_id: int) -> List[LinkedOrganization]:
    """Returns the ERPNext link(s) for an organization (0 or 1). For use by managers for their own org."""
    if org_id is None:
        return []
    return (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.organization_id == org_id)
        .options(joinedload(LinkedOrganization.organization))
        .all()
    )


def delete_linked_organization(db: Session, *, link_id: int, org_id: int) -> Dict[str, Any]:
    """Deletes a linked organization record if it belongs to the given org. Returns data for response."""
    link = (
        db.query(LinkedOrganization)
        .filter(LinkedOrganization.id == link_id, LinkedOrganization.organization_id == org_id)
        .options(joinedload(LinkedOrganization.organization))
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked organization not found.")
    # Build response data before delete (ORM object will be expired after commit)
    result = {
        "id": link.id,
        "organization_id": str(link.organization_id),
        "erpnext_url": link.erpnext_url,
        "api_key": link.api_key,
        "instance_name": link.instance_name,
    }
    db.delete(link)
    db.commit()
    return result


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