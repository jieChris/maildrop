from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from maildrop.app import create_app
from maildrop.config import Settings
from maildrop.db import create_engine_from_url, create_schema, make_session_factory
from maildrop.models import UnassignedMessage
from maildrop.repository import create_alias


RAW = b"From: sender@example.com\nTo: alpha@aiprot.space\nSubject: Hello\n\nBody\n"


def settings() -> Settings:
    return Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        database_url="sqlite+pysqlite:///:memory:",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
    )


def client_with_db(max_message_bytes: int = 26_214_400):
    engine = create_engine_from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    session_factory = make_session_factory(engine)
    app = create_app(settings(), session_factory=session_factory, max_message_bytes=max_message_bytes)
    return TestClient(app, base_url="https://testserver"), session_factory


def test_internal_ingest_requires_token():
    client, _ = client_with_db()

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={"X-Envelope-Recipient": "alpha@aiprot.space"},
    )

    assert response.status_code == 401


def test_internal_ingest_routes_unknown_to_unassigned():
    client, session_factory = client_with_db()

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "unknown@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "unassigned"}
    with session_factory() as db:
        unassigned = db.execute(select(UnassignedMessage)).scalar_one()
    assert unassigned.recipient == "unknown@aiprot.space"
    assert unassigned.reason == "alias_not_registered"


def test_internal_ingest_accepts_docker_bridge_gateway_source():
    engine = create_engine_from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    session_factory = make_session_factory(engine)
    app = create_app(settings(), session_factory=session_factory)
    client = TestClient(
        app,
        base_url="https://testserver",
        client=("172.18.0.1", 50000),
    )

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "unknown@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    assert response.status_code == 202


def test_internal_ingest_routes_non_local_domain_to_unassigned():
    client, session_factory = client_with_db()

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@example.net",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "unassigned"}
    with session_factory() as db:
        unassigned = db.execute(select(UnassignedMessage)).scalar_one()
    assert unassigned.recipient == "alpha@example.net"
    assert unassigned.reason == "domain_not_allowed"


def test_latest_txt_requires_valid_token():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _alias, token = create_alias(db, "alpha", "aiprot.space")

    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    response = client.get("/api/inbox/alpha/latest.txt?token=bad")

    assert response.status_code == 403

    response = client.get(f"/api/inbox/alpha/latest.txt?token={token}")

    assert response.status_code == 200
    assert "Subject: Hello" in response.text
    assert "Body" in response.text


def test_internal_ingest_rejects_oversized_body():
    client, _ = client_with_db(max_message_bytes=4)

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    assert response.status_code == 413


def test_internal_ingest_uses_settings_message_limit_by_default():
    engine = create_engine_from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    session_factory = make_session_factory(engine)
    app_settings = settings().model_copy(update={"max_message_bytes": 4})
    app = create_app(app_settings, session_factory=session_factory)
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    assert response.status_code == 413


def test_public_api_sets_referrer_policy_header():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _alias, token = create_alias(db, "alpha", "aiprot.space")

    response = client.get(f"/api/inbox/alpha/latest.txt?token={token}")

    assert response.headers["referrer-policy"] == "no-referrer"
