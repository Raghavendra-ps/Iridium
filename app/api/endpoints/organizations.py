from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
from app.core.services import organization_service
from app.api import dependencies
from app.db.models import User, LinkedOrganization
from app.db.session import get_db
from app.api.schemas import organization as org_schemas

router = APIRouter()

# Centralize the GOG URL
GOG_GATEWAY_URL = "https://gateway.gretis.com"

@router.get("/", response_model=list[org_schemas.LinkedOrganization])
def read_linked_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """Retrieve all linked organizations for the current user."""
    return db.query(LinkedOrganization).filter(LinkedOrganization.owner_id == current_user.id).all()

@router.post("/", response_model=org_schemas.LinkedOrganization, status_code=status.HTTP_201_CREATED)
async def link_organization(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    org_in: org_schemas.LinkedOrganizationCreate,
):
    """Link a new Organization ID after validating it with the GOG gateway."""
    org_exists_in_db = db.query(LinkedOrganization).filter_by(organization_id=org_in.organization_id, owner_id=current_user.id).first()
    if org_exists_in_db:
        raise HTTPException(status_code=400, detail="This Organization ID has already been linked.")

    # Validate against GOG's public /config endpoint
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{GOG_GATEWAY_URL}/api/v1/org/{org_in.organization_id}/config", timeout=10.0)
        if response.status_code != 200:
             raise HTTPException(status_code=400, detail=f"Invalid Organization ID. GOG returned status {response.status_code}.")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Could not reach the GOG gateway to validate Organization ID.")

    # If valid, create the link
    db_obj = LinkedOrganization(
        organization_id=org_in.organization_id,
        instance_name=org_in.organization_id, # Use the ID as the name for now
        owner_id=current_user.id
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.get("/{link_id}/status")
async def get_organization_status(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """Polls the GOG gateway's public endpoint for status."""
    link = db.query(LinkedOrganization).filter(LinkedOrganization.id == link_id, LinkedOrganization.owner_id == current_user.id).first()
    if not link:
         raise HTTPException(status_code=404, detail="Link not found.")

    test_url = f"{GOG_GATEWAY_URL}/api/v1/org/{link.organization_id}/config"

    # --- START: Improved Polling Logic ---
    try:
        # Define a more generous timeout
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient() as client:
            response = await client.get(test_url, timeout=timeout)

        # This will raise an exception for 4xx or 5xx responses
        response.raise_for_status()

        # If we get here, it's a 2xx success
        return {"status": "online", "details": "Online"}

    except httpx.TimeoutException:
        return {"status": "offline", "details": "Connection timed out. GOG gateway may be slow or unreachable."}
    except httpx.ConnectError:
        return {"status": "offline", "details": "Connection error. Could not connect to the GOG gateway."}
    except httpx.HTTPStatusError as e:
        # Try to parse the error detail from GOG's response
        try:
            detail = e.response.json().get("detail", e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text[:200] # Show first 200 chars if not JSON
        return {"status": "error", "details": f"GOG returned status {e.response.status_code}: {detail}"}
    except Exception as e:
        # Catch any other unexpected errors
        return {"status": "error", "details": f"An unexpected error occurred: {str(e)}"}
    # --- END: Improved Polling Logic ---

@router.delete("/{link_id}", response_model=org_schemas.LinkedOrganization)
def delete_link(
    *,
    link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """Delete a linked organization."""
    link = db.query(LinkedOrganization).filter(LinkedOrganization.id == link_id, LinkedOrganization.owner_id == current_user.id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)
    db.commit()
    return link
