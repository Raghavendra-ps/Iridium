from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from .types import EncryptedString


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="organization", cascade="all, delete-orphan")
    erpnext_link = relationship("LinkedOrganization", back_populates="organization", uselist=False, cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    role = Column(String, nullable=False, default="manager")
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization = relationship("Organization", back_populates="users")
    jobs = relationship("ConversionJob", back_populates="owner", cascade="all, delete-orphan")
    mapping_profiles = relationship("MappingProfile", back_populates="owner", cascade="all, delete-orphan")


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    employee_code = Column(String, nullable=False)
    employee_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    email = Column(String, nullable=True)
    organization = relationship("Organization", back_populates="employees")


class LinkedOrganization(Base):
    __tablename__ = "linked_organizations"
    id = Column(Integer, primary_key=True, index=True)
    # Now links to an organization, not a user. unique=True ensures one-to-one.
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True)
    erpnext_url = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    api_secret = Column(EncryptedString(255), nullable=False)

    organization = relationship("Organization", back_populates="erpnext_link")


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    mapping_profile_id = Column(Integer, ForeignKey("mapping_profiles.id", ondelete="SET NULL"), nullable=True)
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
    target_organization = relationship("Organization") # Now points to the main Organization table
    mapping_profile = relationship("MappingProfile")


class MappingProfile(Base):
    __tablename__ = "mapping_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="mapping_profiles")
    mappings = relationship("AttendanceCodeMapping", back_populates="profile", cascade="all, delete-orphan")


class AttendanceCodeMapping(Base):
    __tablename__ = "attendance_code_mappings"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("mapping_profiles.id"), nullable=False)
    source_code = Column(String, nullable=False)
    target_status = Column(String, nullable=False)

    profile = relationship("MappingProfile", back_populates="mappings")