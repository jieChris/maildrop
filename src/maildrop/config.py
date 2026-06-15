from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_base_url: str = Field(alias="APP_BASE_URL")
    mail_domain: str = Field(alias="MAIL_DOMAIN")
    mail_domains: str = Field(default="", alias="MAIL_DOMAINS")
    mail_registered_subdomains: str = Field(default="", alias="MAIL_REGISTERED_SUBDOMAINS")
    database_url: str = Field(alias="DATABASE_URL")
    admin_username: str = Field(alias="ADMIN_USERNAME")
    admin_password: str = Field(alias="ADMIN_PASSWORD")
    ingest_token: str = Field(alias="INGEST_TOKEN")
    max_message_bytes: int = Field(default=26_214_400, alias="MAX_MESSAGE_BYTES")
    message_retention_days: int = Field(default=180, alias="MESSAGE_RETENTION_DAYS")
    unassigned_retention_days: int = Field(default=30, alias="UNASSIGNED_RETENTION_DAYS")
    spaceship_api_key: str = Field(default="", alias="SPACESHIP_API_KEY")
    spaceship_api_secret: str = Field(default="", alias="SPACESHIP_API_SECRET")
    spaceship_dns_domain: str = Field(default="", alias="SPACESHIP_DNS_DOMAIN")
    spaceship_api_base_url: str = Field(
        default="https://spaceship.dev/api/v1",
        alias="SPACESHIP_API_BASE_URL",
    )
    spaceship_auto_register_txt_prefix: str = Field(
        default="",
        alias="SPACESHIP_AUTO_REGISTER_TXT_PREFIX",
    )
    spaceship_auto_register_parents: str = Field(
        default="",
        alias="SPACESHIP_AUTO_REGISTER_PARENTS",
    )

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

    @property
    def registered_mail_subdomains(self) -> tuple[str, ...]:
        return self._clean_domains(self.mail_registered_subdomains.split(","))

    @property
    def accepted_mail_domains(self) -> tuple[str, ...]:
        domains = [self.mail_domain]
        domains.extend(part.strip() for part in self.mail_domains.split(","))
        domains.extend(self.registered_mail_subdomains)
        return self._clean_domains(domains)

    @property
    def registered_mail_root_domains(self) -> tuple[str, ...]:
        root_domain = self.mail_domain.strip().lower().rstrip(".")
        roots = [root_domain]
        for domain in self._clean_domains(self.mail_domains.split(",")):
            if domain == root_domain or domain.endswith(f".{root_domain}"):
                continue
            roots.append(domain)
        return self._clean_domains(roots)

    @property
    def spaceship_auto_register_parent_domains(self) -> tuple[str, ...]:
        root_domain = self.mail_domain.strip().lower().rstrip(".")
        configured = self._clean_domains(self.spaceship_auto_register_parents.split(","))
        if not configured:
            return (f"exa.{root_domain}",)

        domains: list[str] = []
        for domain in configured:
            clean = domain.strip().lower().strip(".")
            if not clean:
                continue
            if "." not in clean:
                clean = f"{clean}.{root_domain}"
            domains.append(clean)
        return self._clean_domains(domains)

    @staticmethod
    def _clean_domains(domains) -> tuple[str, ...]:
        clean_domains: list[str] = []
        seen: set[str] = set()
        for domain in domains:
            clean = domain.strip().lower()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            clean_domains.append(clean)
        return tuple(clean_domains)


def get_settings() -> Settings:
    return Settings()
