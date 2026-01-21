from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.db.models import User
from app.db.session import get_db
from app.schemas import user as user_schemas
from app.core.services import admin_service

router = APIRouter()

@router.get("/users", response_model=List[user_schemas.UserInDB])
def list_users(
    *,
    db: Session = Depends(get_db),
    # --- START OF FIX: Use the correct dependency name ---
    current_user: User = Depends(dependencies.get_current_superadmin_user),
    # --- END OF FIX ---
):
    """
    List all users in the system.
    (Requires Superadmin privileges)
    """
    users = admin_service.get_all_users(db=db)
    return users

@router.put("/users/{user_id}", response_model=user_schemas.UserInDB)
def update_user(
    *,
    db: Session = Depends(get_db),
    # --- START OF FIX: Use the correct dependency name ---
    current_user: User = Depends(dependencies.get_current_superadmin_user),
    # --- END OF FIX ---
    user_id: int,
    user_in: user_schemas.UserUpdate,
):
    """
    Update a user's role, status, or active state.
    (Requires Superadmin privileges)
    """
    updated_user = admin_service.update_user(db=db, user_id=user_id, user_in=user_in)
    return updated_user