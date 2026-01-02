import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy.orm import Session

from app.api.endpoints import (
    auth,
    conversions,
    dashboard,
    mappings,
    organizations,
    pages,
    users,
)
from app.core.config import settings
from app.db.session import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Gretis DataPort",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)


# --- START OF FIX: ADD THE get_redis DEPENDENCY BACK ---
def get_redis():
    """
    Dependency function that provides a Redis client connection.
    """
    try:
        redis_client = Redis.from_url(settings.REDIS_URI, decode_responses=True)
        redis_client.ping()
        yield redis_client
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        raise HTTPException(status_code=503, detail="Could not connect to Redis.")


    try:
        redis_client = Redis.from_url(settings.REDIS_URI, decode_responses=True)
        redis_client.ping()
        yield redis_client
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        raise HTTPException(status_code=503, detail="Could not connect to Redis.")
# --- END OF FIX ---


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    try:
        db.execute("SELECT 1")
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        db_status = "error"
        raise HTTPException(status_code=503, detail="Database connection error.")

    redis_status = "ok"
    return {
        "status": "ok",
        "dependencies": {"database": db_status, "redis": redis_status},
    }


@app.get("/", tags=["Root"], include_in_schema=False)
def read_root():
    return RedirectResponse(url="/home")


# --- Include API Routers ---
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(
    conversions.router,
    prefix=f"{settings.API_V1_STR}/conversions",
    tags=["conversions"],
)
app.include_router(
    organizations.router,
    prefix=f"{settings.API_V1_STR}/linked-organizations",
    tags=["organizations"],
)
app.include_router(
    dashboard.router,
    prefix=f"{settings.API_V1_STR}/dashboard",
    tags=["dashboard"],
)
app.include_router(
    mappings.router,
    prefix=f"{settings.API_V1_STR}/mapping-profiles",
    tags=["mappings"],
)

app.include_router(pages.router, tags=["pages"])

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
