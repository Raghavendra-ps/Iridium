import httpx
from sqlalchemy.orm import Session
from app.db.models import LinkedOrganization, User
from app.api.schemas.organization import LinkedOrganizationCreate

GOG_GATEWAY_URL = "https://gateway.gretis.com"

async def validate_org_id_with_gog(org_id: str) -> str | None:
    """
    Checks if an org ID is valid by querying the GOG /config endpoint.
    Returns the organization's ID as its name on success, None on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{GOG_GATEWAY_URL}/api/v1/org/{org_id}/config", timeout=10.0)
        if response.status_code == 200:
            return org_id
        return None
    except httpx.RequestError:
        return None

def get_orgs_by_owner(db: Session, *, owner: User) -> list[LinkedOrganization]:
    """Retrieves all organizations linked by a specific user."""
    return db.query(LinkedOrganization).filter(LinkedOrganization.owner_id == owner.id).order_by(LinkedOrganization.instance_name).all()

def link_organization(db: Session, *, obj_in: LinkedOrganizationCreate, owner: User, instance_name: str) -> LinkedOrganization:
    """Creates a new LinkedOrganization record in the database."""
    db_obj = LinkedOrganization(
        organization_id=obj_in.organization_id,
        instance_name=instance_name,
        owner_id=owner.id
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_link(db: Session, *, link_id: int, owner: User) -> LinkedOrganization | None:
    """Deletes a linked organization record, ensuring ownership."""
    db_obj = db.query(LinkedOrganization).filter(LinkedOrganization.id == link_id, LinkedOrganization.owner_id == owner.id).first()
    if db_obj:
        db.delete(db_obj)
        db.commit()
    return db_obj
