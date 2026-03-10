# Iridium-main/app/api/endpoints/dashboard.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.schemas import dashboard as dashboard_schemas
from app.core.services import dashboard_service
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.get("/stats", response_model=dashboard_schemas.DashboardStats)
def get_dashboard_stats(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(dependencies.get_current_user),
) -> dashboard_schemas.DashboardStats:
    """
    Retrieve statistics for the main dashboard, including job counts by
    status and a list of recent activity.
    """
    # 1. Block Employees (Attendance View Only)
    if current_user.role == 'employee':
        # Employees should not be accessing the main dashboard stats
        # They have their own view at /attendance/my-records
        raise HTTPException(status_code=403, detail="Employees restricted to attendance view only.")
        
    # 2. Determine Scope
    # Managers/Superadmins see GLOBAL stats (owner_id=None)
    # Clients see SCOPED stats (owner_id=current_user.id)
    target_owner_id = None
    if current_user.role == 'client':
        target_owner_id = current_user.id
        
    stats = dashboard_service.get_dashboard_stats(db=db, owner_id=target_owner_id)
    return stats
