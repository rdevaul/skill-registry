from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Registry configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    REGISTRY_ADMIN_KEY: str = "change-me-in-production"
    REGISTRY_STORAGE_BACKEND: str = "local"
    REGISTRY_DATA_DIR: str = "./data"
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-west-1"
    REGISTRY_BASE_URL: str = "http://localhost:8400"
    REGISTRY_TITLE: str = "Skill Registry"


settings = Settings()
