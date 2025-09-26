from pydantic import BaseModel

class LinkedOrganizationBase(BaseModel):
    organization_id: str

class LinkedOrganizationCreate(LinkedOrganizationBase):
    pass

class LinkedOrganization(LinkedOrganizationBase):
    id: int
    instance_name: str

    class Config:
        orm_mode = True
