"""Application configuration using Pydantic BaseSettings."""

import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("chipmate.config")


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
    JWT_SECRET: str = "dev-secret-key-change-in-production-min-32-characters-long"

    # CORS Configuration
    FRONTEND_URL: str = "http://localhost:3000"

    # Application Metadata
    APP_VERSION: str = "2.0.0"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Warn if using default JWT_SECRET
        if self.JWT_SECRET == "dev-secret-key-change-in-production-min-32-characters-long":
            logger.warning(
                "⚠️  Using default JWT_SECRET! "
                "This is INSECURE for production. "
                "Set JWT_SECRET environment variable."
            )

    @property
    def cors_origins(self) -> list[str]:
        """Return list of allowed CORS origins."""
        origins = [self.FRONTEND_URL]
        # Add common development ports
        if "localhost" in self.FRONTEND_URL:
            origins.extend([
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ])
        return list(set(origins))


# Global settings instance
settings = Settings()
