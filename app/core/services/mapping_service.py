# Iridium-main/app/core/services/mapping_service.py

from typing import List

from app.api.schemas import mapping as mapping_schemas
from app.db.models import AttendanceCodeMapping, MappingProfile
from fastapi import HTTPException, status
from sqlalchemy.orm import Session


def create_mapping_profile(
    db: Session, *, owner_id: int, profile_in: mapping_schemas.MappingProfileCreate
) -> MappingProfile:
    """Creates a new mapping profile and its associated code mappings."""
    # Check for duplicate profile name for the same user
    existing_profile = (
        db.query(MappingProfile)
        .filter(
            MappingProfile.owner_id == owner_id, MappingProfile.name == profile_in.name
        )
        .first()
    )
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mapping profile with this name already exists.",
        )

    db_profile = MappingProfile(name=profile_in.name, owner_id=owner_id)
    db.add(db_profile)
    db.flush()  # Flush to get the db_profile.id for the mappings

    for mapping in profile_in.mappings:
        db_mapping = AttendanceCodeMapping(
            profile_id=db_profile.id,
            source_code=mapping.source_code.upper(),
            target_status=mapping.target_status,
        )
        db.add(db_mapping)

    db.commit()
    db.refresh(db_profile)
    return db_profile


def get_mapping_profiles_by_owner(
    db: Session, *, owner_id: int
) -> List[MappingProfile]:
    """Retrieves all mapping profiles for a specific user."""
    return (
        db.query(MappingProfile)
        .filter(MappingProfile.owner_id == owner_id)
        .order_by(MappingProfile.name)
        .all()
    )


def delete_mapping_profile(
    db: Session, *, owner_id: int, profile_id: int
) -> MappingProfile:
    """Deletes a mapping profile, ensuring it belongs to the user."""
    db_profile = (
        db.query(MappingProfile)
        .filter(MappingProfile.id == profile_id, MappingProfile.owner_id == owner_id)
        .first()
    )

    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mapping profile not found."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping profile not found.")

    db.delete(db_profile)
    db.commit()
    return db_profile
