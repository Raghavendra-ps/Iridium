# Iridium-main/app/api/schemas/mapping.py

from typing import List

from pydantic import BaseModel, Field

# --- Schemas for Individual Code Mappings ---

class AttendanceCodeMappingBase(BaseModel):
    source_code: str = Field(
        ..., description="The code found in the source file (e.g., 'WO', 'P', 'H')."
    )
    target_status: str = Field(
        ...,
        description="The target ERPNext status ('Absent', 'On Leave', 'Half Day') or 'IGNORE'.",
    )


class AttendanceCodeMappingCreate(AttendanceCodeMappingBase):
    pass


class AttendanceCodeMapping(AttendanceCodeMappingBase):
    id: int

    class Config:
        orm_mode = True


# --- Schemas for Mapping Profiles ---


class MappingProfileBase(BaseModel):
    name: str = Field(
        ..., description="A unique name for the profile, e.g., 'GIPL Factory Policy'."
    )


class MappingProfileCreate(MappingProfileBase):
    mappings: List[AttendanceCodeMappingCreate]


class MappingProfileUpdate(MappingProfileBase):
    mappings: List[AttendanceCodeMappingCreate]

    mappings: List[AttendanceCodeMappingCreate]

class MappingProfile(MappingProfileBase):
    id: int
    owner_id: int
    mappings: List[AttendanceCodeMapping] = []

    class Config:
        orm_mode = True
