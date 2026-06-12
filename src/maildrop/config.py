from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_base_url: str = Field(alias="APP_BASE_URL")
    mail_domain: str = Field(alias="MAIL_DOMAIN")
    database_url: str = Field(alias="DATABASE_URL")
    admin_username: str = Field(alias="ADMIN_USERNAME")
    admin_password: str = Field(alias="ADMIN_PASSWORD")
    ingest_token: str = Field(alias="INGEST_TOKEN")
    max_message_bytes: int = Field(default=26_214_400, alias="MAX_MESSAGE_BYTES")
    message_retention_days: int = Field(default=180, alias="MESSAGE_RETENTION_DAYS")
    unassigned_retention_days: int = Field(default=30, alias="UNASSIGNED_RETENTION_DAYS")

    model_config = SettingsConfigDict(
        env_file=".env.maildrop",
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator(
        "mail_domain",
        "app_base_url",
        "database_url",
        "admin_username",
        "admin_password",
        "ingest_token",
    )
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("max_message_bytes", "message_retention_days", "unassigned_retention_days")
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value


def get_settings() -> Settings:
    return Settings()
