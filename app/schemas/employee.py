from pydantic import BaseModel
from typing import Optional

class EmployeeBase(BaseModel):
    employee_code: str
    employee_name: str
    is_active: bool = True

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    is_active: Optional[bool] = None

class Employee(EmployeeBase):
    id: int
    organization_id: int

    class Config:
        orm_mode = True