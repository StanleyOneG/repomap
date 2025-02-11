"""Application configuration settings."""

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    """Application settings."""

    GITLAB_TOKEN: SecretStr | None = None
    GITHUB_TOKEN: SecretStr | None = None

    class Config:
        """Pydantic configuration."""

        case_sensitive = True
        env_file = ".env"
        extra = "ignore"


settings = Settings()
