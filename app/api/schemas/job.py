from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any

class Job(BaseModel):
    id: int
    owner_id: int
    status: str
    target_doctype: str
    original_filename: str
    created_at: datetime
    error_log: Optional[dict[str, Any]] = None
    class Config:
        orm_mode = True
