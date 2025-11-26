# Iridium-main/Dockerfile.app

# Stage 1: Builder stage
FROM python:3.10-slim-bullseye AS builder
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION=1.4.2
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN apt-get update && apt-get install -y curl && curl -sSL https://install.python-poetry.org | python3 - && apt-get clean
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi

# Stage 2: Production image
FROM python:3.10-slim-bullseye AS production
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV APP_HOME="/app"
RUN groupadd -g 1000 appuser && useradd -u 1000 -g 1000 -m -s /bin/bash appuser
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR $APP_HOME

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv/ ./.venv/

# --- THE ACTUAL FIX ---
# Copy the ENTIRE application context into the image.
# This includes app/, alembic/, frontend/, alembic.ini, etc.
COPY . .

RUN chown -R appuser:appuser $APP_HOME
ENV PATH="$APP_HOME/.venv/bin:$PATH"
EXPOSE 8000
# CMD is now in docker-compose.yml
