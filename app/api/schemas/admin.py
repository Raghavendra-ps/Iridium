from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from datetime import datetime

# The allowed roles and statuses for validation
UserRole = Literal['admin', 'employee', 'client']
UserStatus = Literal['pending', 'active']

class UserUpdate(BaseModel):
    """
    Schema for an admin to update a user's details.
    All fields are optional.
    """
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None

class UserInDB(BaseModel):
    """
    Schema for returning a full user object from the database,
    including role, status, and other details for the admin view.
    """

    id: int
    email: EmailStr
    is_active: bool
    role: UserRole
    status: UserStatus
    created_at: datetime

    class Config:
        orm_mode = True