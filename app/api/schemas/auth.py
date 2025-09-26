from pydantic import BaseModel, EmailStr

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str | None = None

# --- User Schemas ---

# Shared properties for a user
class UserBase(BaseModel):
    email: EmailStr

# Properties to receive via API on user creation
class UserCreate(UserBase):
    password: str

# Properties to return to client
class User(UserBase):
    id: int
    is_active: bool

    class Config:
        # This allows the model to be created from an ORM object
        orm_mode = True
