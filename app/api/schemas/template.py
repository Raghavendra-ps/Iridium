from typing import Any, Dict

from pydantic import BaseModel, Field


class ImportTemplateBase(BaseModel):
    """
    Base schema for an Import Template.
    Defines the core properties of a template.
    """

    name: str = Field(
        ...,
        description="A unique, user-friendly name for the template, e.g., 'Monthly Leave Summary'.",
    )

    # The config field is a flexible JSON object that holds the entire user-defined parsing recipe.
    # The frontend will be responsible for constructing this object based on user input.
    config: Dict[str, Any] = Field(
        ..., description="The user-defined configuration for the parser logic."
    )


class ImportTemplateCreate(ImportTemplateBase):
    """
    Schema used when creating a new Import Template via the API.
    """

    pass


class ImportTemplate(ImportTemplateBase):
    """
    Schema used when returning an Import Template from the API.
    Includes database-generated fields like `id`.
    """

    id: int
    owner_id: int

    class Config:
        orm_mode = True
