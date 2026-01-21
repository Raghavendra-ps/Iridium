# app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from datetime import datetime

# --- User Roles and Statuses ---
# We include 'admin' and 'client' for legacy/compatibility, 
# but 'superadmin', 'manager', 'employee' are your new enterprise roles.
UserRole = Literal['superadmin', 'manager', 'employee', 'admin', 'client']
UserStatus = Literal['pending', 'active']

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

# --- Base User Schemas ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

# --- Schema for API Responses (The one that was failing) ---
class User(UserBase):
    id: int
    is_active: bool
    role: UserRole

    class Config:
        orm_mode = True

# --- Schemas for Admin Management ---
class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None

class UserInDB(User):
    status: UserStatus
    created_at: datetime