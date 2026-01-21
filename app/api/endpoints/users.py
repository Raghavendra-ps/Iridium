from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import dependencies
from app.schemas import user as user_schemas  # <-- CORRECTED IMPORT
from app.db.models import User

router = APIRouter()

@router.get("/me", response_model=user_schemas.User) # Use the new schema
def read_users_me(
    current_user: User = Depends(dependencies.get_current_user)
):
    """
    Get current user.
    """
    return current_user