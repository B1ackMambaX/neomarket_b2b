from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import ClassVar

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    MODERATION_URL: str = "http://moderation:8001"
    B2C_URL: str = "http://b2c:8002"
    B2B_TO_MOD_KEY: str = "changeme"
    B2C_TO_B2B_KEY: str = "changeme"
    B2B_TO_B2C_KEY: str = "changeme"

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # pyright: ignore[reportCallIssue] берем переменные из .env
