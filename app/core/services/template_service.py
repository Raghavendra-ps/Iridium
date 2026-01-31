from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import template as template_schemas
from app.db.models import ImportTemplate

def create_template(
    db: Session, *, owner_id: int, template_in: template_schemas.ImportTemplateCreate
) -> ImportTemplate:
    """
    Creates a new import template for a user.
    """
    # Check if a template with the same name already exists for this user to prevent duplicates.
    existing_template = (
        db.query(ImportTemplate)
        .filter(
            ImportTemplate.owner_id == owner_id, ImportTemplate.name == template_in.name
        )
        .first()
    )

    if existing_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An import template with this name already exists.",
        )

    # Create the new ImportTemplate object using the data from the API schema.
    db_template = ImportTemplate(
        name=template_in.name, config=template_in.config, owner_id=owner_id
    )

    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    return db_template


def get_templates_by_owner(db: Session, *, owner_id: int) -> List[ImportTemplate]:
    """
    Retrieves all import templates created by a specific user.
    """
    return (
        db.query(ImportTemplate)
        .filter(ImportTemplate.owner_id == owner_id)
        .order_by(ImportTemplate.name)
        .all()
    )


def delete_template(db: Session, *, owner_id: int, template_id: int) -> ImportTemplate:
    """
    Deletes an import template, ensuring it belongs to the requesting user.
    """
    db_template = (
        db.query(ImportTemplate)
        .filter(ImportTemplate.id == template_id, ImportTemplate.owner_id == owner_id)
        .first()
    )

    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import template not found."
        )

    db.delete(db_template)
    db.commit()

    return db_template
