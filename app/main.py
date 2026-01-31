import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

# This import remains the same, as all endpoint modules are needed.
from app.api.endpoints import (admin, attendance, auth, conversions, dashboard, employees,
                               linked_organizations, mappings, organizations, pages, sheets,
                               templates, users)
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Gretis DataPort",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    redirect_slashes=False # Add this
)


# --- DEPENDENCIES AND HEALTH CHECKS ---
def get_redis():
    try:
        redis_client = Redis.from_url(settings.REDIS_URI, decode_responses=True)
        redis_client.ping()
        yield redis_client
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        raise HTTPException(status_code=503, detail="Could not connect to Redis.")

@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    db_status = "error"
    redis_status = "error"
    
    try:
        # Explicitly use text() for SQLAlchemy 2.0
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        # We don't raise here yet, so we can check Redis too
        
    try:
        redis.ping()
        redis_status = "ok"
    except Exception as e:
        logger.error(f"Redis connection failed: {str(e)}")

    if db_status == "ok" and redis_status == "ok":
        return {"status": "ok", "dependencies": {"database": db_status, "redis": redis_status}}
    
    raise HTTPException(
        status_code=503, 
        detail={"status": "unhealthy", "database": db_status, "redis": redis_status}
    )

# --- ROUTER INCLUSION (CORRECT AND FINAL ORDER) ---
# 1. All API Routers are included first.
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(conversions.router, prefix=f"{settings.API_V1_STR}/conversions", tags=["conversions"])
app.include_router(organizations.router, prefix=f"{settings.API_V1_STR}/organizations", tags=["organizations"])
app.include_router(linked_organizations.router, prefix=f"{settings.API_V1_STR}/linked-organizations", tags=["linked-organizations"])
app.include_router(employees.router, prefix=f"{settings.API_V1_STR}/employees", tags=["employees"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["dashboard"])
app.include_router(mappings.router, prefix=f"{settings.API_V1_STR}/mapping-profiles", tags=["mappings"])
app.include_router(attendance.router, prefix=f"{settings.API_V1_STR}/attendance", tags=["attendance"])
app.include_router(sheets.router, prefix=f"{settings.API_V1_STR}/sheets", tags=["sheets"])
app.include_router(templates.router, prefix=f"{settings.API_V1_STR}/import-templates", tags=["templates"])
app.include_router(pages.router, tags=["pages"])


# 3. The Root Endpoint is now simple and dependency-free.
@app.get("/", include_in_schema=False)
def read_root():
    """Redirects all root traffic to the /login page."""
    return RedirectResponse(url="/login")

# 4. Static Files are mounted last.
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")