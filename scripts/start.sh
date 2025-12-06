#!/bin/bash
set -e

# activate virtual env if not already in path (Docker handles this, but safety first)
# . /app/.venv/bin/activate

echo "Running Database Initialization..."
python -m app.initial_data

echo "Starting Gunicorn Server..."
exec gunicorn --bind 0.0.0.0:8000 -w 4 -k uvicorn.workers.UvicornWorker --user appuser --group appuser app.main:app
