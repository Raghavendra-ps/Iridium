import os
import sys
from logging.config import fileConfig

# ----------------- BEGIN: Iridium Customization (MOVED TO TOP) -----------------
# This MUST be the first thing to run so that Python can find the 'app' module.
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
# ----------------- END: Iridium Customization -----------------

from sqlalchemy import engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context

from app.core.config import settings
from app.db.base import Base
from app.db import models


# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.attributes.get('configure_logger', True):
    fileConfig(config.config_file_name)

# Override the 'sqlalchemy.url' from alembic.ini with our app's settings.
config.set_main_option('sqlalchemy.url', settings.SQLALCHEMY_DATABASE_URI)

# Point 'target_metadata' to our application's models.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
