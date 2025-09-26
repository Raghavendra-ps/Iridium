import os
from pydantic import BaseSettings, PostgresDsn, RedisDsn
from typing import Optional

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
        return str(PostgresDsn.build(
            scheme="postgresql",
            user=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            path=f"/{self.POSTGRES_DB or ''}",
        ))

    # --- Redis Settings ---
    REDIS_HOST: str
    REDIS_PORT: int

    @property
    def REDIS_URI(self) -> str:
        return str(RedisDsn.build(
            scheme="redis",
            host=self.REDIS_HOST,
            port=str(self.REDIS_PORT),
        ))

    # --- Celery Settings ---
    # These MUST be defined at the class level, not inside a function.
    # We are reusing the REDIS_URI property we defined above.
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
