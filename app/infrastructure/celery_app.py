from celery import Celery
from celery.signals import worker_process_init
from app.core.config import settings
from app.db.session import engine # Import the engine object

# This signal is sent by Celery when a worker process is initialized.
# We use it to dispose of the old database engine connection pool.
# This prevents the forked worker process from using stale connections
# from the parent (Gunicorn) process. This is the definitive fix.
@worker_process_init.connect
def init_worker(**kwargs):
    engine.dispose()

# Initialize Celery
celery = Celery("iridium_worker")

# Load configuration from our central settings object
celery.config_from_object(settings, namespace='CELERY')

# Tell Celery to automatically discover tasks
celery.autodiscover_tasks(packages=["app.infrastructure"])
