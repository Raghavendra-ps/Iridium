from sqlalchemy import text, inspect
from app.db.session import SessionLocal, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    db = SessionLocal()
    try:
        logger.info("Checking if is_archived column exists...")
        inspector = inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('conversion_jobs')]
        
        if 'is_archived' in columns:
            logger.info("Column 'is_archived' already exists. Skipping.")
        else:
            logger.info("Adding 'is_archived' column to conversion_jobs table...")
            # Postgres syntax for adding column
            db.execute(text("ALTER TABLE conversion_jobs ADD COLUMN is_archived BOOLEAN DEFAULT FALSE"))
            db.commit()
            logger.info("Migration successful!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
