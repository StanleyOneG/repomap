"""Application configuration settings."""

import os

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings."""

    # GitLab Configuration
    GITLAB_BASE_URL: str = os.getenv("GITLAB_BASE_URL")
    GITLAB_TOKEN: SecretStr | None

    class Config:
        """Pydantic configuration."""

        case_sensitive = True
        env_file = ".env"


# Create global settings instance
settings = Settings()
