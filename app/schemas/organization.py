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

class ERPNextLink(ERPNextLinkBase):
    class Config:
        orm_mode = True


class OrganizationBase(BaseModel):
    name: str

class OrganizationCreate(OrganizationBase):
    pass

class Organization(OrganizationBase):
    id: int
    created_at: datetime
    erpnext_link: Optional[ERPNextLink] = None
    users: List[UserInDB] = []
    employees: List[Employee] = []

    class Config:
        orm_mode = True

# Update forward references after all models are defined
Organization.update_forward_refs()