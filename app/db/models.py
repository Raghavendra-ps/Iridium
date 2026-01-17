from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from .types import EncryptedString


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jobs = relationship("ConversionJob", back_populates="owner")
    linked_organizations = relationship(
        "LinkedOrganization", back_populates="owner", cascade="all, delete-orphan"
    )
    mapping_profiles = relationship(
        "MappingProfile", back_populates="owner", cascade="all, delete-orphan"
    )


class LinkedOrganization(Base):
    __tablename__ = "linked_organizations"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, nullable=False)
    instance_name = Column(String, nullable=False)
    erpnext_url = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    api_secret = Column(EncryptedString(255), nullable=False)

    owner = relationship("User", back_populates="linked_organizations")


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_org_id = Column(
        Integer, ForeignKey("linked_organizations.id"), nullable=True
    )
    mapping_profile_id = Column(
        Integer, ForeignKey("mapping_profiles.id", ondelete="SET NULL"), nullable=True
    )
    parsing_config = Column(JSON, nullable=True)

    attendance_year = Column(Integer, nullable=True)
    attendance_month = Column(Integer, nullable=True)

    status = Column(String, default="UPLOADED", nullable=False)
    target_doctype = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    storage_filename = Column(String, unique=True, nullable=False)

    raw_data_path = Column(String, nullable=True)
    processed_data_path = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_log = Column(JSON, nullable=True)

    owner = relationship("User", back_populates="jobs")
    target_organization = relationship("LinkedOrganization")
    mapping_profile = relationship("MappingProfile")


class MappingProfile(Base):
    __tablename__ = "mapping_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="mapping_profiles")
    mappings = relationship(
        "AttendanceCodeMapping",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class AttendanceCodeMapping(Base):
    __tablename__ = "attendance_code_mappings"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("mapping_profiles.id"), nullable=False)
    source_code = Column(String, nullable=False)
    target_status = Column(String, nullable=False)

    profile = relationship("MappingProfile", back_populates="mappings")


# The ImportTemplate model is no longer needed and has been removed.
