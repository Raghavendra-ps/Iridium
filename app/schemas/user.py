# app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from datetime import datetime

# --- User Role and Status Literals ---
UserRole = Literal['superadmin', 'manager', 'client', 'employee']
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
    organization_id: Optional[int] = None # For choosing existing
    organization_name: Optional[str] = None # For creating new

# --- Schema for API Responses (The one that was failing) ---
class User(UserBase):
    id: int
    is_active: bool
    role: UserRole
    organization_id: Optional[int] = None
    class Config:
        orm_mode = True

# --- Schemas for Admin Management ---
class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    organization_id: Optional[int] = None
class UserInDB(User):
    status: UserStatus
    created_at: datetime