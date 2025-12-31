# Iridium-main/app/api/endpoints/mappings.py

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import mapping as mapping_schemas
from app.core.services import mapping_service
from app.db.models import User
from app.db.session import get_db

router = APIRouter()

@router.post(
    "/",
    response_model=mapping_schemas.MappingProfile,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping_profile(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    profile_in: mapping_schemas.MappingProfileCreate,
):
    """Create a new attendance code mapping profile."""
    return mapping_service.create_mapping_profile(
        db=db, owner_id=current_user.id, profile_in=profile_in
    )


@router.get("/", response_model=List[mapping_schemas.MappingProfile])
def list_user_mapping_profiles(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """List all mapping profiles for the current user."""
    return mapping_service.get_mapping_profiles_by_owner(
        db=db, owner_id=current_user.id
    )


@router.delete("/{profile_id}", response_model=mapping_schemas.MappingProfile)
def delete_mapping_profile(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    profile_id: int,
):
    """Delete a mapping profile."""
    return mapping_service.delete_mapping_profile(
        db=db, owner_id=current_user.id, profile_id=profile_id
    )
    return mapping_service.delete_mapping_profile(db=db, owner_id=current_user.id, profile_id=profile_id)
