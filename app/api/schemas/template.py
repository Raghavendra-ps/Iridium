# Iridium-main/app/api/schemas/template.py

from typing import Any, Dict

from pydantic import BaseModel, Field

class ImportTemplateBase(BaseModel):
    name: str = Field(
        ...,
        description="A unique name for the template, e.g., 'Monthly Leave Summary'.",
    )
    config: Dict[str, Any] = Field(
        ..., description="The user-defined configuration for the parser logic."
    )


class ImportTemplateCreate(ImportTemplateBase):
    pass

class ImportTemplateCreate(ImportTemplateBase):
    pass

class ImportTemplate(ImportTemplateBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True
