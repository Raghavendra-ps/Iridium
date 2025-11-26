# Iridium-main/app/core/config.py

import os
from typing import Optional
from urllib.parse import quote_plus

from pydantic import BaseSettings, PostgresDsn, RedisDsn


class Settings(BaseSettings):
    # --- Application Settings ---
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str

    # --- Database Settings ---
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # URL-encode the username and password to handle special characters
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        server = self.POSTGRES_SERVER
        db = self.POSTGRES_DB

        # --- THE FIX ---
        # Build the URI and then escape any '%' characters for Alembic's config parser.
        uri = f"postgresql://{user}:{password}@{server}/{db}"
        return uri.replace("%", "%%")
        # --- END OF FIX ---

    # --- Redis Settings ---
    REDIS_HOST: str
    REDIS_PORT: int

    @property
    def REDIS_URI(self) -> str:
        return str(
            RedisDsn.build(
                scheme="redis",
                host=self.REDIS_HOST,
                port=str(self.REDIS_PORT),
            )
        )

    # --- Celery Settings ---
    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URI

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URI

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
