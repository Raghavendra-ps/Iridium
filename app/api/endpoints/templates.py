# Iridium-main/app/api/endpoints/templates.py

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import template as template_schemas
from app.core.services import template_service
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.post(
    "/",
    response_model=template_schemas.ImportTemplate,
    status_code=status.HTTP_201_CREATED,
)
def create_import_template(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    template_in: template_schemas.ImportTemplateCreate,
):
    """Create a new import template."""
    return template_service.create_template(
        db=db, owner_id=current_user.id, template_in=template_in
    )


@router.get("/", response_model=List[template_schemas.ImportTemplate])
def list_user_import_templates(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
):
    """List all import templates for the current user."""
    return template_service.get_templates_by_owner(db=db, owner_id=current_user.id)


@router.delete("/{template_id}", response_model=template_schemas.ImportTemplate)
def delete_import_template(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
    template_id: int,
):
    """Delete an import template."""
    return template_service.delete_template(
        db=db, owner_id=current_user.id, template_id=template_id
    )
