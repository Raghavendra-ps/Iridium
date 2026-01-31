# Iridium-main/app/api/schemas/organization.py

from pydantic import BaseModel, HttpUrl


class LinkedOrganizationBase(BaseModel):
    organization_id: str
    # --- START: Add new fields for ERPNext ---
    erpnext_url: HttpUrl  # Pydantic will validate this is a valid URL
    api_key: str
    # --- END: Add new fields ---


class LinkedOrganizationCreate(LinkedOrganizationBase):
    # --- Add the secret only for creation ---
    api_secret: str

class LinkedOrganization(LinkedOrganizationBase):
    id: int
    instance_name: str
    # We explicitly DO NOT include api_secret here.
    # It should never be sent back to the client after being set.

    class Config:
        orm_mode = True
