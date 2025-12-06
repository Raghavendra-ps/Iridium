# Iridium-main/app/initial_data.py
import logging

from app.db.base import Base

# Import all models here so Base knows about them
from app.db.models import ConversionJob, LinkedOrganization, User
from app.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    logger.info("Creating initial database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        # We don't raise here to allow the app to attempt startup
        # even if tables exist, but strictly speaking, we should handle this via Alembic.


if __name__ == "__main__":
    init_db()
