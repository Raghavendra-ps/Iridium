# Iridium-main/app/infrastructure/celery_app.py

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.db.session import engine

@worker_process_init.connect
def init_worker(**kwargs):
    engine.dispose()

def init_worker(**kwargs):
    engine.dispose()

celery = Celery("iridium_worker")

# --- THE FIX ---
# Instead of using a namespace, we will explicitly configure the two
# most important settings. This is more robust.
celery.conf.broker_url = settings.CELERY_BROKER_URL
celery.conf.result_backend = settings.CELERY_RESULT_BACKEND
# --- END OF FIX ---

celery.autodiscover_tasks(packages=["app.infrastructure"])
