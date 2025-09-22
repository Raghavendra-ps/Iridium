# Stage 1: Builder stage to install dependencies
FROM python:3.10-slim-bullseye AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION=1.4.2
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Install poetry
RUN apt-get update && apt-get install -y curl \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get clean

# Add poetry to path
ENV PATH="$POETRY_HOME/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml poetry.lock ./

# Install project dependencies
# --no-dev: Excludes development dependencies for the final image
# We install them here to cache the layers, but will only copy prod deps later
RUN poetry install --no-interaction --no-ansi

# Stage 2: Production image
FROM python:3.10-slim-bullseye AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERed 1
ENV APP_HOME="/app"

# Create a non-root user for security
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Install necessary system dependencies for the application
# We add `libpq-dev` which is needed by psycopg2 to connect to PostgreSQL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR $APP_HOME

# Copy the virtual environment with dependencies from the builder stage
COPY --from=builder /app/.venv/ ./.venv/

# Activate the virtual environment
ENV PATH="$APP_HOME/.venv/bin:$PATH"

# Copy the application source code
COPY ./app ./app

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appuser $APP_HOME

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000
