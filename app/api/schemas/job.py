from pydantic import BaseModel
from datetime import datetime

class Job(BaseModel):
    id: int
    owner_id: int
    status: str
    target_doctype: str
    original_filename: str
    created_at: datetime

    class Config:
        orm_mode = True
