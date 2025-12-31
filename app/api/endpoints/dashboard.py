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
    stats = dashboard_service.get_dashboard_stats(db=db, owner_id=current_user.id)
    return stats
