from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import auth as auth_schemas
from app.db.models import User

router = APIRouter() # <-- THIS LINE WAS MISSING

@router.get("/me", response_model=auth_schemas.User)
def read_users_me(
    current_user: User = Depends(dependencies.get_current_user)
):
    """
    Get current user.
    """
    return current_user
