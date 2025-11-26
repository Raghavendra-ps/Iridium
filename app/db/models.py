# Iridium-main/app/db/models.py

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

# --- Add this import ---
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


class LinkedOrganization(Base):
    __tablename__ = "linked_organizations"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, nullable=False)
    instance_name = Column(String, nullable=False)

    # --- START: New fields for ERPNext integration ---
    erpnext_url = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    # This field uses our custom type to automatically encrypt the secret.
    api_secret = Column(
        EncryptedString(255), nullable=False
    )  # Specify a length for the underlying String
    # --- END: New fields ---

    owner = relationship("User", back_populates="linked_organizations")


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # This links to our new table
    target_org_id = Column(
        Integer, ForeignKey("linked_organizations.id"), nullable=True
    )

    status = Column(String, default="UPLOADED", nullable=False)
    target_doctype = Column(String, nullable=False)
    operation = Column(String, default="CREATE", nullable=False)
    original_filename = Column(String, nullable=False)
    storage_filename = Column(String, unique=True, nullable=False)
    intermediate_data_path = Column(String, nullable=True)
    final_output_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_log = Column(JSON, nullable=True)

    owner = relationship("User", back_populates="jobs")
    target_organization = relationship("LinkedOrganization")
