# Lightweight Mail API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the licensed EmailEngine deployment with a lightweight self-hosted receive-only mail system for `aiprot.space`, with catch-all SMTP intake, alias management, unassigned mail review, and per-alias API links for latest messages.

**Architecture:** Postfix receives all mail for `aiprot.space` and pipes each message to a local HTTP ingest endpoint on the FastAPI app. The app parses the MIME message, stores registered alias mail in PostgreSQL, stores unknown recipients in an unassigned queue, and serves a Basic-Auth admin UI plus tokenized public read APIs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Jinja2, pytest, httpx, Docker Compose, Caddy, Postfix.

**Commit status:** This repository started with no commits. The per-task commit
steps below are marked complete by the consolidated initial project commit after
all tasks, deployment, DNS cutover, production checks, and public SMTP smoke
tests passed.

---

## File Structure

Create application code under `src/maildrop/`:

- `src/maildrop/config.py`: environment parsing and typed settings.
- `src/maildrop/db.py`: SQLAlchemy engine/session helpers.
- `src/maildrop/models.py`: database tables for aliases, messages, unassigned messages, and ingest events.
- `src/maildrop/schemas.py`: Pydantic response models for API JSON.
- `src/maildrop/security.py`: admin Basic Auth and token hashing helpers.
- `src/maildrop/mailparse.py`: MIME parsing, recipient normalization, and body extraction.
- `src/maildrop/repository.py`: database operations for aliases and messages.
- `src/maildrop/app.py`: FastAPI app, admin pages, public APIs, internal ingest endpoint.
- `src/maildrop/cli.py`: CLI utilities for retention cleanup.
- `src/maildrop/templates/*.html`: Jinja2 admin pages.
- `src/maildrop/static/admin.css`: compact admin styling.

Create tests under `tests/maildrop/`:

- `tests/maildrop/conftest.py`: test app and temporary SQLite database fixtures.
- `tests/maildrop/test_mailparse.py`: MIME parsing behavior.
- `tests/maildrop/test_repository.py`: alias/message persistence behavior.
- `tests/maildrop/test_api.py`: public API and ingest endpoint behavior.
- `tests/maildrop/test_admin.py`: admin auth and bulk alias generation behavior.

Create deployment files:

- `pyproject.toml`: Python package and dependencies.
- `Dockerfile`: application image.
- `docker-compose.maildrop.yml`: app + PostgreSQL deployment.
- `.env.maildrop.example`: deploy-time config template.
- `deploy/postfix/main.cf.maildrop`: Postfix settings to receive `aiprot.space`.
- `deploy/postfix/master.cf.maildrop`: Postfix pipe transport service.
- `deploy/postfix/mail-api-ingest`: host script called by Postfix pipe.
- `deploy/caddy/Caddyfile.maildrop`: reverse proxy for the new app.
- `docs/maildrop-ops.md`: DNS, Postfix, deployment, backup, and rollback commands.

Existing files to modify:

- `README.md`: replace EmailEngine-centric instructions with Maildrop service instructions while preserving the historical EmailEngine notes in a short migration section.
- `Caddyfile`: update proxy target from EmailEngine `127.0.0.1:3000` to Maildrop `127.0.0.1:8000` after the app is deployed.
- `.gitignore`: add Python, test, and local database artifacts.

---

## Task 1: Python Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/maildrop/__init__.py`
- Create: `src/maildrop/config.py`
- Create: `tests/maildrop/test_config.py`
- Modify: `.gitignore`

- [x] **Step 1: Write the failing config test**

Create `tests/maildrop/test_config.py`:

```python
import pytest

from maildrop.config import Settings


def test_settings_reads_required_values():
    settings = Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        database_url="postgresql+psycopg://maildrop:secret@postgres:5432/maildrop",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
    )

    assert settings.app_base_url == "https://aiprot.space"
    assert settings.mail_domain == "aiprot.space"
    assert settings.admin_username == "admin"
    assert settings.ingest_token == "ingest-secret"


def test_settings_rejects_empty_mail_domain():
    with pytest.raises(ValueError):
        Settings(
            app_base_url="https://aiprot.space",
            mail_domain="",
            database_url="sqlite+pysqlite:///:memory:",
            admin_username="admin",
            admin_password="admin-secret",
            ingest_token="ingest-secret",
        )
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/maildrop/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'maildrop'`.

- [x] **Step 3: Create package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "maildrop"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic==1.17.2",
  "beautifulsoup4==4.14.2",
  "fastapi==0.124.0",
  "httpx==0.28.1",
  "jinja2==3.1.6",
  "psycopg[binary]==3.3.2",
  "pydantic-settings==2.12.0",
  "python-multipart==0.0.20",
  "sqlalchemy==2.0.45",
  "uvicorn[standard]==0.38.0",
]

[project.optional-dependencies]
dev = [
  "pytest==9.0.2",
  "pytest-asyncio==1.3.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Create `src/maildrop/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

- [x] **Step 4: Implement settings**

Create `src/maildrop/config.py`:

```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_base_url: str = Field(alias="APP_BASE_URL")
    mail_domain: str = Field(alias="MAIL_DOMAIN")
    database_url: str = Field(alias="DATABASE_URL")
    admin_username: str = Field(alias="ADMIN_USERNAME")
    admin_password: str = Field(alias="ADMIN_PASSWORD")
    ingest_token: str = Field(alias="INGEST_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env.maildrop",
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("mail_domain", "app_base_url", "database_url", "admin_username", "admin_password", "ingest_token")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


def get_settings() -> Settings:
    return Settings()
```

- [x] **Step 5: Update `.gitignore`**

Append:

```gitignore
.env.maildrop
.pytest_cache/
__pycache__/
*.pyc
*.sqlite3
htmlcov/
dist/
build/
*.egg-info/
```

- [x] **Step 6: Run tests**

Run:

```bash
python -m pytest tests/maildrop/test_config.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

Run:

```bash
git add pyproject.toml src/maildrop/__init__.py src/maildrop/config.py tests/maildrop/test_config.py .gitignore
git commit -m "chore: scaffold maildrop python project"
```

---

## Task 2: Database Models and Session Layer

**Files:**
- Create: `src/maildrop/db.py`
- Create: `src/maildrop/models.py`
- Create: `tests/maildrop/conftest.py`
- Create: `tests/maildrop/test_models.py`

- [x] **Step 1: Write model tests**

Create `tests/maildrop/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from maildrop.models import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session
```

Create `tests/maildrop/test_models.py`:

```python
from maildrop.models import Alias, Message, UnassignedMessage


def test_alias_message_relationship(db_session):
    alias = Alias(prefix="alpha", email="alpha@aiprot.space", api_token_hash="hash", enabled=True)
    db_session.add(alias)
    db_session.flush()

    message = Message(
        alias_id=alias.id,
        recipient="alpha@aiprot.space",
        sender="sender@example.com",
        subject="Hello",
        text_body="Plain body",
        html_body="<p>Plain body</p>",
        raw_mime="raw",
        headers_json={"message-id": "<1@example.com>"},
    )
    db_session.add(message)
    db_session.commit()

    stored = db_session.get(Alias, alias.id)
    assert stored.email == "alpha@aiprot.space"
    assert stored.messages[0].subject == "Hello"


def test_unassigned_message_records_unknown_recipient(db_session):
    item = UnassignedMessage(
        recipient="unknown@aiprot.space",
        sender="sender@example.com",
        subject="Unknown",
        text_body="Body",
        raw_mime="raw",
        headers_json={},
        reason="alias_not_registered",
    )
    db_session.add(item)
    db_session.commit()

    assert db_session.query(UnassignedMessage).one().recipient == "unknown@aiprot.space"
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/maildrop/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'maildrop.models'`.

- [x] **Step 3: Implement models**

Create `src/maildrop/models.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("prefix", name="uq_alias_prefix"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    api_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list["Message"]] = relationship(back_populates="alias", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias_id: Mapped[int] = mapped_column(ForeignKey("aliases.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    text_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_mime: Mapped[str] = mapped_column(Text, nullable=False)
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    alias: Mapped[Alias] = relationship(back_populates="messages")


class UnassignedMessage(Base):
    __tablename__ = "unassigned_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    text_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_mime: Mapped[str] = mapped_column(Text, nullable=False)
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)


class IngestEvent(Base):
    __tablename__ = "ingest_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
```

- [x] **Step 4: Implement session helpers**

Create `src/maildrop/db.py`. Do not read environment variables or create a global engine at import time; the FastAPI app will inject the production database URL later.

```python
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.session import sessionmaker as SessionMaker

from maildrop.models import Base


def create_engine_from_url(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def make_session_factory(engine: Engine) -> SessionMaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def get_db_from_factory(session_factory: SessionMaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session
```

- [x] **Step 5: Run model tests**

Run:

```bash
python -m pytest tests/maildrop/test_models.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
git add src/maildrop/db.py src/maildrop/models.py tests/maildrop/conftest.py tests/maildrop/test_models.py
git commit -m "feat: add maildrop database models"
```

---

## Task 3: MIME Parsing and Recipient Normalization

**Files:**
- Create: `src/maildrop/mailparse.py`
- Create: `tests/maildrop/test_mailparse.py`

- [x] **Step 1: Write parser tests**

Create `tests/maildrop/test_mailparse.py`:

```python
from maildrop.mailparse import ParsedMessage, normalize_recipient, parse_message


RAW = """From: Sender <sender@example.com>
To: Alpha <alpha@aiprot.space>
Subject: =?utf-8?b?5rWL6K+V?=
Message-ID: <m1@example.com>
Content-Type: multipart/alternative; boundary="b"

--b
Content-Type: text/plain; charset=utf-8

Hello plain
--b
Content-Type: text/html; charset=utf-8

<p>Hello <b>html</b></p>
--b--
"""


def test_normalize_recipient_lowercases_domain_and_prefix():
    assert normalize_recipient("Alpha@AIPROT.SPACE") == "alpha@aiprot.space"


def test_parse_message_extracts_subject_sender_and_bodies():
    parsed = parse_message(RAW.encode("utf-8"), "alpha@aiprot.space")

    assert isinstance(parsed, ParsedMessage)
    assert parsed.recipient == "alpha@aiprot.space"
    assert parsed.sender == "sender@example.com"
    assert parsed.subject == "测试"
    assert parsed.text_body.strip() == "Hello plain"
    assert "Hello" in parsed.html_body
    assert parsed.headers["message-id"] == "<m1@example.com>"
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/maildrop/test_mailparse.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'maildrop.mailparse'`.

- [x] **Step 3: Implement parser**

Create `src/maildrop/mailparse.py`:

```python
from dataclasses import dataclass
from email import policy
from email.headerregistry import Address
from email.parser import BytesParser
from email.utils import parseaddr

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ParsedMessage:
    recipient: str
    sender: str
    subject: str
    text_body: str
    html_body: str
    raw_mime: str
    headers: dict[str, str]


def normalize_recipient(value: str) -> str:
    value = value.strip().strip("<>").lower()
    _, address = parseaddr(value)
    address = (address or value).strip().lower()
    if "@" not in address:
        raise ValueError("recipient must contain @")
    local, domain = address.rsplit("@", 1)
    if not local or not domain:
        raise ValueError("recipient local part and domain must be non-empty")
    return f"{local}@{domain}"


def _sender_address(value: object) -> str:
    if not value:
        return ""
    addresses = getattr(value, "addresses", None)
    if addresses:
        first = addresses[0]
        if isinstance(first, Address):
            return first.addr_spec
    _, address = parseaddr(str(value))
    return address


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def parse_message(raw: bytes, envelope_recipient: str) -> ParsedMessage:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    recipient = normalize_recipient(envelope_recipient)

    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = part.get_content_disposition()
            content_type = part.get_content_type()
            if content_disposition == "attachment":
                continue
            if content_type == "text/plain" and not text_body:
                text_body = part.get_content()
            elif content_type == "text/html" and not html_body:
                html_body = part.get_content()
    else:
        content_type = msg.get_content_type()
        if content_type == "text/html":
            html_body = msg.get_content()
        else:
            text_body = msg.get_content()

    if not text_body and html_body:
        text_body = _html_to_text(html_body)

    headers = {key.lower(): str(value) for key, value in msg.items()}

    return ParsedMessage(
        recipient=recipient,
        sender=_sender_address(msg["from"]),
        subject=str(msg["subject"] or ""),
        text_body=text_body or "",
        html_body=html_body or "",
        raw_mime=raw.decode("utf-8", errors="replace"),
        headers=headers,
    )
```

- [x] **Step 4: Run parser tests**

Run:

```bash
python -m pytest tests/maildrop/test_mailparse.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add src/maildrop/mailparse.py tests/maildrop/test_mailparse.py
git commit -m "feat: parse incoming email messages"
```

---

## Task 4: Repository Operations

**Files:**
- Create: `src/maildrop/repository.py`
- Create: `src/maildrop/security.py`
- Create: `tests/maildrop/test_repository.py`

- [x] **Step 1: Write repository tests**

Create `tests/maildrop/test_repository.py`:

```python
from maildrop.mailparse import ParsedMessage
from maildrop.repository import (
    create_alias,
    generate_aliases,
    ingest_parsed_message,
    latest_message_for_alias,
)
from maildrop.security import verify_token
from maildrop.models import Alias, UnassignedMessage


def parsed(recipient: str) -> ParsedMessage:
    return ParsedMessage(
        recipient=recipient,
        sender="sender@example.com",
        subject="Subject",
        text_body="Body",
        html_body="<p>Body</p>",
        raw_mime="raw",
        headers={},
    )


def test_create_alias_stores_hash_and_returns_plain_token(db_session):
    alias, token = create_alias(db_session, "alpha", "aiprot.space")

    assert alias.email == "alpha@aiprot.space"
    assert token
    assert alias.api_token_hash != token
    assert verify_token(token, alias.api_token_hash)


def test_ingest_registered_alias_stores_message(db_session):
    alias, _ = create_alias(db_session, "alpha", "aiprot.space")

    result = ingest_parsed_message(db_session, parsed("alpha@aiprot.space"), expected_domain="aiprot.space")

    latest = latest_message_for_alias(db_session, alias)
    assert result == "assigned"
    assert latest.subject == "Subject"
    assert alias.message_count == 1


def test_ingest_unknown_alias_goes_to_unassigned(db_session):
    result = ingest_parsed_message(db_session, parsed("unknown@aiprot.space"), expected_domain="aiprot.space")

    assert result == "unassigned"
    assert db_session.query(UnassignedMessage).one().recipient == "unknown@aiprot.space"


def test_ingest_other_domain_goes_to_unassigned(db_session):
    create_alias(db_session, "alpha", "aiprot.space")

    result = ingest_parsed_message(db_session, parsed("alpha@example.net"), expected_domain="aiprot.space")

    stored = db_session.query(UnassignedMessage).one()
    assert result == "unassigned"
    assert stored.recipient == "alpha@example.net"
    assert stored.reason == "domain_not_allowed"


def test_generate_aliases_creates_requested_count(db_session):
    created = generate_aliases(db_session, "aiprot.space", count=3, length=10)

    assert len(created) == 3
    assert db_session.query(Alias).count() == 3
    assert all(item[0].email.endswith("@aiprot.space") for item in created)
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/maildrop/test_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'maildrop.repository'`.

- [x] **Step 3: Implement token helpers**

Create `src/maildrop/security.py`:

```python
import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)
```

- [x] **Step 4: Implement repository**

Create `src/maildrop/repository.py`:

```python
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from maildrop.mailparse import ParsedMessage, normalize_recipient
from maildrop.models import Alias, Message, UnassignedMessage
from maildrop.security import hash_token, new_token


ALPHABET = string.ascii_lowercase + string.digits


def prefix_from_email(email: str) -> str:
    return normalize_recipient(email).split("@", 1)[0]


def create_alias(db: Session, prefix: str, domain: str, note: str = "", commit: bool = True) -> tuple[Alias, str]:
    clean_prefix = prefix.strip().lower()
    if not clean_prefix:
        raise ValueError("prefix must not be empty")
    if any(ch not in ALPHABET + "-_." for ch in clean_prefix):
        raise ValueError("prefix contains unsupported characters")

    token = new_token()
    alias = Alias(
        prefix=clean_prefix,
        email=f"{clean_prefix}@{domain.lower()}",
        api_token_hash=hash_token(token),
        enabled=True,
        note=note,
    )
    db.add(alias)
    db.flush()
    if commit:
        db.commit()
        db.refresh(alias)
    return alias, token


def generate_aliases(db: Session, domain: str, count: int, length: int = 12) -> list[tuple[Alias, str]]:
    if count < 1 or count > 1000:
        raise ValueError("count must be between 1 and 1000")
    if length < 6 or length > 32:
        raise ValueError("length must be between 6 and 32")

    created: list[tuple[Alias, str]] = []
    existing = {row[0] for row in db.execute(select(Alias.prefix)).all()}

    while len(created) < count:
        prefix = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if prefix in existing:
            continue
        alias, token = create_alias(db, prefix, domain, commit=False)
        existing.add(prefix)
        created.append((alias, token))

    db.commit()
    for alias, _token in created:
        db.refresh(alias)
    return created


def find_alias_by_prefix(db: Session, prefix: str) -> Alias | None:
    return db.execute(select(Alias).where(Alias.prefix == prefix.lower())).scalar_one_or_none()


def ingest_parsed_message(db: Session, parsed: ParsedMessage, expected_domain: str) -> str:
    recipient = normalize_recipient(parsed.recipient)
    prefix, domain = recipient.rsplit("@", 1)
    if domain != expected_domain.lower():
        db.add(
            UnassignedMessage(
                recipient=recipient,
                sender=parsed.sender,
                subject=parsed.subject,
                text_body=parsed.text_body,
                html_body=parsed.html_body,
                raw_mime=parsed.raw_mime,
                headers_json=parsed.headers,
                reason="domain_not_allowed",
            )
        )
        db.commit()
        return "unassigned"

    alias = find_alias_by_prefix(db, prefix)

    if not alias or not alias.enabled:
        db.add(
            UnassignedMessage(
                recipient=parsed.recipient,
                sender=parsed.sender,
                subject=parsed.subject,
                text_body=parsed.text_body,
                html_body=parsed.html_body,
                raw_mime=parsed.raw_mime,
                headers_json=parsed.headers,
                reason="alias_not_registered" if not alias else "alias_disabled",
            )
        )
        db.commit()
        return "unassigned"

    now = datetime.now(timezone.utc)
    db.add(
        Message(
            alias_id=alias.id,
            recipient=parsed.recipient,
            sender=parsed.sender,
            subject=parsed.subject,
            text_body=parsed.text_body,
            html_body=parsed.html_body,
            raw_mime=parsed.raw_mime,
            headers_json=parsed.headers,
            received_at=now,
        )
    )
    alias.last_message_at = now
    alias.message_count += 1
    db.commit()
    return "assigned"


def latest_message_for_alias(db: Session, alias: Alias) -> Message | None:
    return (
        db.execute(
            select(Message)
            .where(Message.alias_id == alias.id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
```

- [x] **Step 5: Run repository tests**

Run:

```bash
python -m pytest tests/maildrop/test_repository.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
git add src/maildrop/security.py src/maildrop/repository.py tests/maildrop/test_repository.py
git commit -m "feat: add alias and message repository"
```

---

## Task 5: FastAPI Ingest and Public API

Implementation correction from review:

- `create_app(settings, session_factory=None, max_message_bytes=26214400)` must support explicit session factory injection for tests.
- The app must not depend on a global engine/session created at import time.
- `/internal/ingest` must require `X-Ingest-Token`, reject non-local callers, enforce `max_message_bytes`, and call `ingest_parsed_message(db, parsed, expected_domain=settings.mail_domain)`.
- Public API responses must include `Referrer-Policy: no-referrer` because tokenized links use query strings.
- `/api/health` must verify that the app can talk to the database with a lightweight query.
- Deployment must start FastAPI with an app factory instead of relying on a module-level `app = create_app()`.

**Files:**
- Create: `src/maildrop/schemas.py`
- Create: `src/maildrop/app.py`
- Create: `tests/maildrop/test_api.py`

- [x] **Step 1: Write API tests**

Create `tests/maildrop/test_api.py`:

```python
from fastapi.testclient import TestClient

from maildrop.app import create_app
from maildrop.config import Settings
from maildrop.db import get_db
from maildrop.models import Base
from maildrop.repository import create_alias
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


RAW = b"From: sender@example.com\nTo: alpha@aiprot.space\nSubject: Hello\n\nBody\n"


def client_with_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    settings = Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        database_url="sqlite+pysqlite:///:memory:",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
    )
    app = create_app(settings)

    def override_db():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), SessionLocal


def test_internal_ingest_requires_token():
    client, _ = client_with_db()

    response = client.post("/internal/ingest", content=RAW, headers={"X-Envelope-Recipient": "alpha@aiprot.space"})

    assert response.status_code == 401


def test_internal_ingest_routes_unknown_to_unassigned():
    client, _ = client_with_db()

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={"X-Envelope-Recipient": "unknown@aiprot.space", "X-Ingest-Token": "ingest-secret"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "unassigned"}


def test_latest_txt_requires_valid_token():
    client, SessionLocal = client_with_db()
    with SessionLocal() as db:
        alias, token = create_alias(db, "alpha", "aiprot.space")

    client.post(
        "/internal/ingest",
        content=RAW,
        headers={"X-Envelope-Recipient": "alpha@aiprot.space", "X-Ingest-Token": "ingest-secret"},
    )

    bad = client.get("/api/inbox/alpha/latest.txt?token=bad")
    good = client.get(f"/api/inbox/alpha/latest.txt?token={token}")

    assert bad.status_code == 403
    assert good.status_code == 200
    assert "Subject: Hello" in good.text
    assert "Body" in good.text
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/maildrop/test_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'maildrop.app'`.

- [x] **Step 3: Implement schemas**

Create `src/maildrop/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: int
    recipient: str
    sender: str
    subject: str
    received_at: datetime
    text_body: str
```

- [x] **Step 4: Implement FastAPI app**

Create `src/maildrop/app.py`:

```python
from collections.abc import Generator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from maildrop.config import Settings, get_settings
from maildrop.db import create_schema, get_db
from maildrop.mailparse import parse_message
from maildrop.models import Alias, Message
from maildrop.repository import find_alias_by_prefix, ingest_parsed_message, latest_message_for_alias
from maildrop.schemas import MessageOut
from maildrop.security import verify_token


def settings_dep() -> Settings:
    return get_settings()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title="Maildrop", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    def startup() -> None:
        create_schema()

    @app.post("/internal/ingest", status_code=202)
    async def ingest(
        request: Request,
        x_envelope_recipient: str = Header(alias="X-Envelope-Recipient"),
        x_ingest_token: str = Header(default="", alias="X-Ingest-Token"),
        db: Session = Depends(get_db),
    ) -> dict[str, str]:
        if x_ingest_token != app_settings.ingest_token:
            raise HTTPException(status_code=401, detail="invalid ingest token")
        raw = await request.body()
        parsed = parse_message(raw, x_envelope_recipient)
        status = ingest_parsed_message(db, parsed)
        return {"status": status}

    def authorized_alias(prefix: str, token: str, db: Session) -> Alias:
        alias = find_alias_by_prefix(db, prefix)
        if not alias:
            raise HTTPException(status_code=404, detail="alias not found")
        if not alias.enabled:
            raise HTTPException(status_code=403, detail="alias disabled")
        if not verify_token(token, alias.api_token_hash):
            raise HTTPException(status_code=403, detail="invalid token")
        return alias

    @app.get("/api/inbox/{prefix}/latest.txt", response_class=PlainTextResponse)
    def latest_txt(prefix: str, token: str = Query(...), db: Session = Depends(get_db)) -> str:
        alias = authorized_alias(prefix, token, db)
        message = latest_message_for_alias(db, alias)
        if not message:
            raise HTTPException(status_code=404, detail="no messages")
        return (
            f"From: {message.sender}\n"
            f"To: {message.recipient}\n"
            f"Subject: {message.subject}\n"
            f"Received: {message.received_at.isoformat()}\n\n"
            f"{message.text_body}"
        )

    @app.get("/api/inbox/{prefix}/latest.json", response_model=MessageOut)
    def latest_json(prefix: str, token: str = Query(...), db: Session = Depends(get_db)) -> Message:
        alias = authorized_alias(prefix, token, db)
        message = latest_message_for_alias(db, alias)
        if not message:
            raise HTTPException(status_code=404, detail="no messages")
        return message

    @app.get("/api/inbox/{prefix}/messages.json", response_model=list[MessageOut])
    def messages_json(prefix: str, token: str = Query(...), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> list[Message]:
        alias = authorized_alias(prefix, token, db)
        return list(
            db.execute(
                select(Message)
                .where(Message.alias_id == alias.id)
                .order_by(Message.received_at.desc(), Message.id.desc())
                .limit(limit)
            ).scalars()
        )

    return app


app = create_app()
```

- [x] **Step 5: Run API tests**

Run:

```bash
python -m pytest tests/maildrop/test_api.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
git add src/maildrop/schemas.py src/maildrop/app.py tests/maildrop/test_api.py
git commit -m "feat: add ingest and public inbox api"
```

---

## Task 6: Admin UI and Bulk Alias Generation

Implementation correction from review:

- Admin must use application Basic Auth from `Settings.admin_username` and `Settings.admin_password`.
- Admin POST routes must require CSRF validation.
- `/admin` must support `q`, `page`, and `page_size` so 1000+ aliases remain manageable.
- `/admin/unassigned` must support pagination.
- The UI should be a compact Chinese operational dashboard. It must not be a landing page.
- Token plaintext is only shown immediately after generation; existing aliases display `token-hidden-after-creation` in generated API URL placeholders.

**Files:**
- Modify: `src/maildrop/app.py`
- Create: `src/maildrop/templates/base.html`
- Create: `src/maildrop/templates/aliases.html`
- Create: `src/maildrop/templates/unassigned.html`
- Create: `src/maildrop/templates/messages.html`
- Create: `src/maildrop/static/admin.css`
- Create: `tests/maildrop/test_admin.py`

- [x] **Step 1: Write admin tests**

Create `tests/maildrop/test_admin.py`:

```python
from base64 import b64encode

from tests.maildrop.test_api import client_with_db


def auth_header(user="admin", password="admin-secret"):
    token = b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_requires_basic_auth():
    client, _ = client_with_db()

    response = client.get("/admin")

    assert response.status_code == 401


def test_admin_bulk_generates_aliases():
    client, _ = client_with_db()

    response = client.post("/admin/aliases/bulk", data={"count": "2", "length": "8"}, headers=auth_header())

    assert response.status_code == 200
    assert response.text.count("@aiprot.space") >= 2
    assert "/api/inbox/" in response.text
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/maildrop/test_admin.py -v
```

Expected: FAIL because `/admin` route is missing.

- [x] **Step 3: Add admin templates**

Create `src/maildrop/templates/base.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} - Maildrop</title>
  <link rel="stylesheet" href="/static/admin.css">
</head>
<body>
  <header>
    <h1>Maildrop</h1>
    <nav>
      <a href="/admin">邮箱别名</a>
      <a href="/admin/unassigned">未登记邮件</a>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

Create `src/maildrop/templates/aliases.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>邮箱别名</h2>
<form method="post" action="/admin/aliases/bulk" class="toolbar">
  <label>生成数量 <input type="number" name="count" min="1" max="1000" value="10"></label>
  <label>前缀长度 <input type="number" name="length" min="6" max="32" value="12"></label>
  <button type="submit">批量生成</button>
</form>
<table>
  <thead>
    <tr><th>邮箱</th><th>状态</th><th>邮件数</th><th>最后收信</th><th>API 链接</th></tr>
  </thead>
  <tbody>
    {% for item in aliases %}
    <tr>
      <td>{{ item.alias.email }}</td>
      <td>{{ "启用" if item.alias.enabled else "禁用" }}</td>
      <td>{{ item.alias.message_count }}</td>
      <td>{{ item.alias.last_message_at or "" }}</td>
      <td><code>{{ item.latest_txt_url }}</code></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% if generated %}
<h3>本次生成</h3>
<textarea readonly rows="10">{% for item in generated %}{{ item.email }} {{ item.latest_txt_url }}
{% endfor %}</textarea>
{% endif %}
{% endblock %}
```

Create `src/maildrop/templates/unassigned.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>未登记邮件</h2>
<table>
  <thead>
    <tr><th>收件人</th><th>发件人</th><th>主题</th><th>时间</th><th>原因</th></tr>
  </thead>
  <tbody>
    {% for message in messages %}
    <tr>
      <td>{{ message.recipient }}</td>
      <td>{{ message.sender }}</td>
      <td>{{ message.subject }}</td>
      <td>{{ message.received_at }}</td>
      <td>{{ message.reason }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `src/maildrop/templates/messages.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>{{ alias.email }}</h2>
<table>
  <thead>
    <tr><th>发件人</th><th>主题</th><th>时间</th></tr>
  </thead>
  <tbody>
    {% for message in messages %}
    <tr>
      <td>{{ message.sender }}</td>
      <td>{{ message.subject }}</td>
      <td>{{ message.received_at }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `src/maildrop/static/admin.css`:

```css
body {
  color: #1f2937;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
  background: #f8fafc;
}

header {
  background: #111827;
  color: #fff;
  padding: 16px 24px;
}

header h1 {
  font-size: 20px;
  margin: 0 0 8px;
}

nav a {
  color: #d1d5db;
  margin-right: 16px;
  text-decoration: none;
}

main {
  padding: 24px;
}

.toolbar {
  align-items: center;
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

input, button, textarea {
  font: inherit;
}

button {
  background: #2563eb;
  border: 0;
  color: white;
  cursor: pointer;
  padding: 8px 12px;
}

table {
  background: white;
  border-collapse: collapse;
  width: 100%;
}

th, td {
  border-bottom: 1px solid #e5e7eb;
  padding: 10px;
  text-align: left;
  vertical-align: top;
}

code, textarea {
  font-family: "SFMono-Regular", Consolas, monospace;
}

textarea {
  width: 100%;
}
```

- [x] **Step 4: Add admin routes to `src/maildrop/app.py`**

Modify `src/maildrop/app.py` by adding imports:

```python
import secrets
from fastapi import Form
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from maildrop.repository import generate_aliases
from maildrop.models import UnassignedMessage
```

Inside `create_app`, after `app = FastAPI(...)`, add:

```python
    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    templates = Jinja2Templates(directory=str(template_dir))
    basic = HTTPBasic()
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def require_admin(credentials: HTTPBasicCredentials = Depends(basic)) -> str:
        valid_user = secrets.compare_digest(credentials.username, app_settings.admin_username)
        valid_password = secrets.compare_digest(credentials.password, app_settings.admin_password)
        if not (valid_user and valid_password):
            raise HTTPException(status_code=401, detail="invalid admin credentials", headers={"WWW-Authenticate": "Basic"})
        return credentials.username

    def alias_view(alias: Alias, token: str | None = None) -> dict[str, str | Alias]:
        api_token = token or "token-hidden-after-creation"
        latest_txt_url = f"{app_settings.app_base_url}/api/inbox/{alias.prefix}/latest.txt?token={api_token}"
        return {"alias": alias, "latest_txt_url": latest_txt_url}
```

Add admin routes before `return app`:

```python
    @app.get("/admin", response_class=HTMLResponse)
    def admin_aliases(request: Request, _: str = Depends(require_admin), db: Session = Depends(get_db)) -> HTMLResponse:
        aliases = db.execute(select(Alias).order_by(Alias.created_at.desc(), Alias.id.desc()).limit(1000)).scalars().all()
        return templates.TemplateResponse(
            "aliases.html",
            {"request": request, "title": "邮箱别名", "aliases": [alias_view(alias) for alias in aliases], "generated": []},
        )

    @app.post("/admin/aliases/bulk", response_class=HTMLResponse)
    def admin_bulk_aliases(
        request: Request,
        count: int = Form(...),
        length: int = Form(...),
        _: str = Depends(require_admin),
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        generated_pairs = generate_aliases(db, app_settings.mail_domain, count=count, length=length)
        aliases = db.execute(select(Alias).order_by(Alias.created_at.desc(), Alias.id.desc()).limit(1000)).scalars().all()
        generated = [
            {"email": alias.email, "latest_txt_url": alias_view(alias, token)["latest_txt_url"]}
            for alias, token in generated_pairs
        ]
        return templates.TemplateResponse(
            "aliases.html",
            {"request": request, "title": "邮箱别名", "aliases": [alias_view(alias) for alias in aliases], "generated": generated},
        )

    @app.get("/admin/unassigned", response_class=HTMLResponse)
    def admin_unassigned(request: Request, _: str = Depends(require_admin), db: Session = Depends(get_db)) -> HTMLResponse:
        messages = db.execute(
            select(UnassignedMessage).order_by(UnassignedMessage.received_at.desc(), UnassignedMessage.id.desc()).limit(200)
        ).scalars().all()
        return templates.TemplateResponse(
            "unassigned.html",
            {"request": request, "title": "未登记邮件", "messages": messages},
        )
```

- [x] **Step 5: Run admin tests**

Run:

```bash
python -m pytest tests/maildrop/test_admin.py -v
```

Expected: PASS.

- [x] **Step 6: Run all app tests**

Run:

```bash
python -m pytest tests/maildrop -v
```

Expected: PASS.

- [x] **Step 7: Commit**

Run:

```bash
git add src/maildrop/app.py src/maildrop/templates src/maildrop/static tests/maildrop/test_admin.py
git commit -m "feat: add admin alias management ui"
```

---

## Task 7: Docker Compose Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.maildrop.yml`
- Create: `.env.maildrop.example`
- Modify: `README.md`

- [x] **Step 1: Create `.env.maildrop.example`**

Create:

```dotenv
APP_BASE_URL=https://aiprot.space
MAIL_DOMAIN=aiprot.space
DATABASE_URL=postgresql+psycopg://maildrop:change-postgres-password@postgres:5432/maildrop
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-admin-password
INGEST_TOKEN=change-ingest-token
POSTGRES_DB=maildrop
POSTGRES_USER=maildrop
POSTGRES_PASSWORD=change-postgres-password
```

- [x] **Step 2: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "maildrop.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [x] **Step 3: Create Compose file**

Create `docker-compose.maildrop.yml`:

```yaml
name: maildrop

services:
  app:
    build: .
    restart: unless-stopped
    env_file:
      - .env.maildrop
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file:
      - .env.maildrop
    volumes:
      - maildrop-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\""]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

volumes:
  maildrop-postgres:
```

- [x] **Step 4: Add health endpoint**

Already implemented in Task 5. The endpoint must execute a lightweight database query and return:

```json
{"success": true}
```

- [x] **Step 5: Add health test**

Already implemented in Task 5.

```python
def test_health_endpoint():
    client, _ = client_with_db()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"success": True}
```

- [x] **Step 6: Run tests**

Run:

```bash
python -m pytest tests/maildrop -v
```

Expected: PASS.

- [x] **Step 7: Build image locally**

Run:

```bash
cp .env.maildrop.example .env.maildrop
python - <<'PY'
from pathlib import Path
p = Path(".env.maildrop")
text = p.read_text()
text = text.replace("change-postgres-password", "local-postgres-secret")
text = text.replace("change-admin-password", "local-admin-secret")
text = text.replace("change-ingest-token", "local-ingest-secret")
p.write_text(text)
PY
docker compose -f docker-compose.maildrop.yml config --quiet
docker compose -f docker-compose.maildrop.yml build
```

Expected: Compose config succeeds and image builds.

Status on 2026-06-12: local Docker is not installed in this workspace environment (`zsh:1: command not found: docker`), so the local build step was superseded by a server-side production build. Static local checks were run, then `docker compose -f docker-compose.maildrop.yml up -d --build` completed on `/opt/maildrop` and both `app` and `postgres` reported healthy during production validation.

```bash
ruby -e 'require "yaml"; data = YAML.load_file("docker-compose.maildrop.yml"); abort("missing app") unless data.dig("services", "app"); abort("missing postgres") unless data.dig("services", "postgres"); abort("app port not local") unless data.dig("services", "app", "ports").include?("127.0.0.1:8000:8000"); puts "compose yaml ok"'
ruby -e 'text = File.read("Dockerfile"); abort("not using factory") unless text.include?("maildrop.app:create_app") && text.include?("--factory"); puts "dockerfile factory ok"'
```

- [x] **Step 8: Commit**

Run:

```bash
git add Dockerfile docker-compose.maildrop.yml .env.maildrop.example src/maildrop/app.py tests/maildrop/test_api.py README.md
git commit -m "chore: add maildrop docker deployment"
```

---

## Task 8: Postfix Catch-All Delivery

**Files:**
- Create: `deploy/postfix/main.cf.maildrop`
- Create: `deploy/postfix/master.cf.maildrop`
- Create: `deploy/postfix/mail-api-ingest`
- Create: `docs/maildrop-ops.md`

- [x] **Step 1: Create Postfix main config snippet**

Create `deploy/postfix/main.cf.maildrop`:

```text
myhostname = mail.aiprot.space
myorigin = /etc/mailname
inet_interfaces = all
inet_protocols = ipv4
mydestination = localhost
relay_domains =
smtpd_relay_restrictions = permit_mynetworks reject_unauth_destination

virtual_mailbox_domains = aiprot.space
virtual_mailbox_maps = regexp:/etc/postfix/virtual_mailbox_regexp
virtual_transport = mailapi
mailapi_destination_recipient_limit = 1

message_size_limit = 26214400
mailbox_size_limit = 0
```

- [x] **Step 2: Create virtual mailbox regexp**

Document in `docs/maildrop-ops.md` that `/etc/postfix/virtual_mailbox_regexp` must contain:

```text
/^.+@aiprot\.space$/ catchall
```

- [x] **Step 3: Create Postfix master transport snippet**

Create `deploy/postfix/master.cf.maildrop`:

```text
mailapi unix - n n - - pipe
  flags=Rq user=mailapi argv=/usr/local/bin/mail-api-ingest ${recipient}
```

- [x] **Step 4: Create ingest script**

Create `deploy/postfix/mail-api-ingest`.

Final status: implemented in `deploy/postfix/mail-api-ingest`. The final script
uses a shared `tempfail` path for all temporary failures, verifies that
`/etc/mail-api-ingest.env` is readable, checks `INGEST_TOKEN`, allows
`INGEST_URL` override for operations, maps only HTTP `2xx` to success, and
returns exit `75` for all ingest failures so Postfix retries safely.

- [x] **Step 5: Create operations doc**

Create `docs/maildrop-ops.md` with these deployment commands:

```markdown
# Maildrop Operations

## DNS

Set these records for `aiprot.space`:

```text
mail.aiprot.space.  A    167.71.29.22
aiprot.space.       MX   10 mail.aiprot.space.
aiprot.space.       TXT  "v=spf1 -all"
_dmarc.aiprot.space TXT  "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
```

## Deploy app

```bash
openssl rand -hex 24
cp .env.maildrop.example .env.maildrop
vim .env.maildrop
docker compose -f docker-compose.maildrop.yml up -d --build
curl -fsS http://127.0.0.1:8000/api/health
```

## Install Postfix

```bash
apt-get update
apt-get install -y postfix curl
useradd -r -s /usr/sbin/nologin mailapi || true
install -m 0755 deploy/postfix/mail-api-ingest /usr/local/bin/mail-api-ingest
tmp_env="$(mktemp)"
printf 'INGEST_TOKEN=%s\n' "$(grep '^INGEST_TOKEN=' .env.maildrop | cut -d= -f2-)" > "$tmp_env"
install -o root -g mailapi -m 0640 "$tmp_env" /etc/mail-api-ingest.env
rm -f "$tmp_env"
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  postconf -e "$line"
done < deploy/postfix/main.cf.maildrop
printf '/^.+@aiprot\\.space$/ catchall\n' > /etc/postfix/virtual_mailbox_regexp
postmap -q 'probe@aiprot.space' regexp:/etc/postfix/virtual_mailbox_regexp
postconf -M -e 'mailapi/unix=mailapi unix - n n - - pipe flags=Rq user=mailapi argv=/usr/local/bin/mail-api-ingest ${recipient}'
postfix check
sudo -u mailapi sh -c '. /etc/mail-api-ingest.env; test -n "$INGEST_TOKEN"'
systemctl restart postfix
systemctl enable postfix
```

## Verify

```bash
dig +short MX aiprot.space @1.1.1.1
swaks --to testunknown@aiprot.space --from sender@example.net --server 127.0.0.1
docker compose -f docker-compose.maildrop.yml logs --tail=100 app
```

Unknown recipients appear in `/admin/unassigned`.
```

- [x] **Step 6: Commit**

Run:

```bash
git add deploy/postfix docs/maildrop-ops.md
git commit -m "docs: add postfix catch-all deployment plan"
```

---

## Task 9: Caddy Cutover and EmailEngine Shutdown

**Files:**
- Create: `deploy/caddy/Caddyfile.maildrop`
- Modify: `Caddyfile`
- Modify: `README.md`

- [x] **Step 1: Create new Caddy config**

Create `deploy/caddy/Caddyfile.maildrop`:

```text
aiprot.space, www.aiprot.space, engine.aiprot.space {
    handle /internal/* {
        respond 404
    }

    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

- [x] **Step 2: Modify root `Caddyfile`**

Replace the current reverse proxy target:

```text
reverse_proxy 127.0.0.1:3000
```

with:

```text
reverse_proxy 127.0.0.1:8000
```

Remove the old site-wide Caddy Basic Auth because Maildrop protects `/admin` itself and public API links must remain directly accessible. Keep `/internal/*` blocked at Caddy.

- [x] **Step 3: Stop EmailEngine after Maildrop health is green**

Run on the server:

```bash
ssh emailengine 'cd /opt/emailengine && docker compose stop emailengine redis'
```

Expected: EmailEngine containers stop. Do not remove volumes until Maildrop has received real test mail.

- [x] **Step 4: Deploy Caddy cutover**

Run:

```bash
rsync -av --delete --exclude .git --exclude .playwright-cli --exclude output ./ emailengine:/opt/maildrop/
ssh emailengine 'cp /opt/maildrop/Caddyfile /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy'
```

Expected: Caddy reload succeeds.

- [x] **Step 5: Verify HTTPS**

Run:

```bash
curl -I -u 'admin:<ADMIN_PASSWORD>' https://aiprot.space/admin
curl -fsS https://aiprot.space/api/health
```

Expected: `/admin` returns `200` with Basic Auth, `/api/health` returns `{"success":true}`.

- [x] **Step 6: Commit**

Run:

```bash
git add deploy/caddy/Caddyfile.maildrop Caddyfile README.md
git commit -m "chore: prepare caddy cutover to maildrop"
```

---

## Task 10: Production Deployment and Smoke Test

**Files:**
- Modify: `README.md`
- Modify: `docs/maildrop-ops.md`

- [x] **Step 1: Generate production secrets**

Run locally:

```bash
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
```

Use the three outputs for:

```text
POSTGRES_PASSWORD
ADMIN_PASSWORD
INGEST_TOKEN
```

- [x] **Step 2: Create server `.env.maildrop`**

Run:

```bash
ssh emailengine 'cd /opt/maildrop && cp .env.maildrop.example .env.maildrop && chmod 600 .env.maildrop'
```

Edit `/opt/maildrop/.env.maildrop` on the server with:

```dotenv
APP_BASE_URL=https://aiprot.space
MAIL_DOMAIN=aiprot.space
DATABASE_URL=postgresql+psycopg://maildrop:<POSTGRES_PASSWORD>@postgres:5432/maildrop
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<ADMIN_PASSWORD>
INGEST_TOKEN=<INGEST_TOKEN>
MAX_MESSAGE_BYTES=26214400
POSTGRES_DB=maildrop
POSTGRES_USER=maildrop
POSTGRES_PASSWORD=<POSTGRES_PASSWORD>
```

- [x] **Step 3: Start Maildrop**

Run:

```bash
ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml up -d --build'
ssh emailengine 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml ps'
```

Expected: `app` and `postgres` are `healthy`.

- [x] **Step 4: Install Postfix config**

Run the commands from `docs/maildrop-ops.md` under "Install Postfix".

Expected:

```bash
postfix check
systemctl is-active postfix
```

prints no errors and `active`.

- [x] **Step 5: Update DNS**

Set DNS records:

```text
mail.aiprot.space A 167.71.29.22
aiprot.space MX 10 mail.aiprot.space
aiprot.space TXT "v=spf1 -all"
_dmarc.aiprot.space TXT "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
```

This receive-only policy assumes there is no legitimate sending path for `aiprot.space`.

Verify:

```bash
dig +short A mail.aiprot.space @1.1.1.1
dig +short MX aiprot.space @1.1.1.1
```

Expected: `167.71.29.22` and `10 mail.aiprot.space.`

Status on 2026-06-12: complete. `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` exited `0` and confirmed exact Maildrop DNS cutover, HTTPS, Docker, Postfix, and public SMTP 25 reachability.

- [x] **Step 6: Smoke test SMTP to unassigned**

Run from the server:

```bash
printf 'Subject: Smoke Test\nFrom: sender@example.net\nTo: unknown-%s@aiprot.space\n\nSmoke body\n' "$(date +%s)" \
  | /usr/local/bin/mail-api-ingest "unknown-$(date +%s)@aiprot.space"
```

Expected: command exits `0`; the recipient appears in `unassigned_messages`.


- [x] **Step 7: Smoke test registered alias API**

Use the admin UI at `https://aiprot.space/admin` to generate one alias, copy its `latest.txt` URL, then send a message to that alias:

```bash
printf 'Subject: Registered Smoke\nFrom: sender@example.net\nTo: <generated>@aiprot.space\n\nRegistered body\n' \
  | /usr/local/bin/mail-api-ingest "<generated>@aiprot.space"
curl -fsS '<copied latest.txt URL>'
```

Expected: output contains:

```text
Subject: Registered Smoke
Registered body
```

- [x] **Step 8: Commit docs update**

Status on 2026-06-12: before the DNS provider is updated, run:

```bash
scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22
```

Historical pre-cutover result was exit `2` with all service checks passing and DNS warnings for `mail.aiprot.space`, MX, SPF, and DMARC. After DNS is changed, exit `0` is the acceptance gate for production DNS cutover.

Status on 2026-06-12 after Spaceship DNS cutover: exit `0`. A real public SMTP smoke test also passed:

```bash
scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22
```

Result: `PASS public SMTP smoke delivered to unassigned: public-smoke-1781235189-308aaa04@aiprot.space`.

Run:

```bash
git add README.md docs/maildrop-ops.md
git commit -m "docs: document maildrop production deployment"
```

---

## Self-Review

Spec coverage:

- Catch-all MX to own server: covered by Tasks 8 and 10.
- No sending/replying: architecture uses receive-only Postfix and SPF `-all`.
- Registered aliases: covered by Tasks 4 and 6.
- Unregistered mail list: covered by Tasks 2, 4, and 6.
- Per-alias latest plain-text API links: covered by Task 5; existing aliases can rotate token from the admin UI if a link is lost.
- JSON API and latest message access: covered by Task 5.
- Bulk random prefix generation: covered by Tasks 4 and 6.
- 1000 aliases maintainability: database-backed aliases, indexed prefix/email, admin search and pagination for alias, unassigned, and per-alias message lists; regression coverage verifies large alias sets and paginated mail views.
- Long-term operations: covered by Docker, Postfix, DNS, backup-oriented PostgreSQL storage, retention cleanup, token rotation, access-log hardening, and docs.

Placeholder scan:

- No `TBD`, `TODO`, or "fill in later" text remains.
- Production secrets are generated in Task 10 and inserted into `.env.maildrop` before deployment.

Type consistency:

- `Alias`, `Message`, and `UnassignedMessage` names are consistent across models, repository, API, and templates.
- `INGEST_TOKEN`, `MAIL_DOMAIN`, and `APP_BASE_URL` environment names are consistent across config, Docker, Postfix script, and docs.
