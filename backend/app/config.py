"""Application configuration using Pydantic BaseSettings."""

import logging
import os
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("chipmate.config")

# Development-only default for JWT_SECRET
_DEV_JWT_SECRET = "dev-secret-key-change-in-production-min-32-characters-long"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # MongoDB Configuration
    MONGO_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "chipmate"

    # Authentication
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    JWT_SECRET: Optional[str] = None

    # CORS Configuration
    # Comma-separated list of allowed origins, or "*" for all origins
    CORS_ORIGINS: str = ""

    # Application Metadata
    APP_VERSION: str = "2.0.0"
    
    @field_validator("JWT_SECRET", mode="before")
    @classmethod
    def validate_jwt_secret(cls, v):
        """Validate JWT_SECRET and provide development default with warning."""
        if v is None or v == "":
            # Only use default if not in production (Railway sets RAILWAY_ENVIRONMENT)
            is_production = os.getenv("RAILWAY_ENVIRONMENT") == "production"
            if is_production:
                raise ValueError(
                    "JWT_SECRET must be set in production. "
                    "This is a critical security requirement."
                )
            logger.warning(
                "⚠️  JWT_SECRET not set! Using development default. "
                "This is INSECURE for production. "
                "Set JWT_SECRET environment variable."
            )
            return _DEV_JWT_SECRET
        return v

    @property
    def cors_origins(self) -> list[str]:
        """Return list of allowed CORS origins.

        If CORS_ORIGINS is empty, allows all origins in development
        (localhost:3000, localhost:5173) but returns empty in production.

        Set CORS_ORIGINS environment variable to a comma-separated list
        of allowed origins, or "*" for all origins.
        """
        if self.CORS_ORIGINS:
            if self.CORS_ORIGINS == "*":
                return ["*"]
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

        # Default development origins if not in production
        is_production = os.getenv("RAILWAY_ENVIRONMENT") == "production"
        if is_production:
            logger.warning(
                "CORS_ORIGINS not configured in production. "
                "Set CORS_ORIGINS environment variable."
            )
            return []

        # Development defaults
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]


# Global settings instance
settings = Settings()
