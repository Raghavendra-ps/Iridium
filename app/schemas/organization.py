from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from datetime import datetime

# Forward-declare schemas to handle circular relationships
from .user import UserInDB
from .employee import Employee

class ERPNextLinkBase(BaseModel):
    erpnext_url: HttpUrl
    api_key: str

class ERPNextLinkCreate(ERPNextLinkBase):
    api_secret: str
    organization_id: Optional[int] = None

class ERPNextLink(ERPNextLinkBase):
    class Config:
        orm_mode = True


class OrganizationBase(BaseModel):
    name: str

class OrganizationCreate(OrganizationBase):
    pass

class Organization(OrganizationBase):
    id: int
    source: Optional[str] = "internal"  # 'internal' | 'external'
    created_at: datetime
    erpnext_link: Optional[ERPNextLink] = None
    users: List[UserInDB] = []
    employees: List[Employee] = []

    class Config:
        orm_mode = True


class OrganizationForDropdown(BaseModel):
    """Lightweight org for sheet maker / dropdowns; includes internal vs external label."""
    id: int
    name: str
    source: str  # 'internal' | 'external'
    is_linked: bool  # Whether it has an ERPNext link


class ExternalOrganizationCreate(BaseModel):
    """Create an external company (ERPNext) in one step: org + link."""
    name: str
    erpnext_url: HttpUrl
    api_key: str
    api_secret: str

# Update forward references after all models are defined
Organization.update_forward_refs()