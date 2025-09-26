from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from redis import Redis
import logging

from app.core.config import settings
from app.db.session import SessionLocal, get_db
# --- Ensure ALL routers are imported with correct names ---
from app.api.endpoints import auth, users, pages, conversions, organizations

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Iridium - Data Conversion Service",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- Dependency for Redis Connection ---
def get_redis():
    try:
        redis_client = Redis.from_url(settings.REDIS_URI, decode_responses=True)
        redis_client.ping()
        yield redis_client
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        raise HTTPException(status_code=503, detail="Could not connect to Redis.")

# --- Endpoints defined in main.py ---
@app.get("/health", tags=["Health"])
def health_check(
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    try:
        db.execute("SELECT 1")
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        db_status = "error"
        raise HTTPException(status_code=503, detail="Database connection error.")
    redis_status = "ok"
    return {"status": "ok", "dependencies": {"database": db_status, "redis": redis_status}}

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to Iridium"}

# --- Include API Routers from other files ---
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(conversions.router, prefix=f"{settings.API_V1_STR}/conversions", tags=["conversions"])
# This now uses the correct variable name 'organizations'
app.include_router(organizations.router, prefix=f"{settings.API_V1_STR}/linked-organizations", tags=["organizations"])

# --- Include Page Routers ---
app.include_router(pages.router, tags=["pages"])
