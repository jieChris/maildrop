from base64 import b64encode
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlparse

import httpx

from maildrop.config import Settings
from maildrop.models import Alias, ManagedInbox, Message, RegisteredSubdomain, UnassignedMessage
from maildrop.repository import create_alias
from tests.maildrop.test_api import RAW, client_with_db


def auth_header(user: str = "admin", password: str = "admin-secret") -> dict[str, str]:
    token = b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def csrf_token_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def exported_token_for(export_text: str, prefix: str) -> str:
    match = re.search(
        rf"{prefix}@aiprot\.space https://aiprot\.space/api/inbox/{prefix}/latest\.txt\?token=([A-Za-z0-9_-]+)",
        export_text,
    )
    assert match is not None
    return match.group(1)


def test_admin_requires_basic_auth():
    client, _session_factory = client_with_db()

    response = client.get("/admin")

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


def test_authenticated_admin_index_returns_aliases():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_alias(db, "alpha", "aiprot.space")

    response = client.get("/admin", headers=auth_header())

    assert response.status_code == 200
    assert "邮箱别名" in response.text
    assert "alpha@aiprot.space" in response.text
    assert "token-hidden-after-creation" in response.text


def test_admin_sets_hardened_csrf_cookie():
    client, _session_factory = client_with_db()

    response = client.get("/admin", headers=auth_header())

    cookie_header = response.headers["set-cookie"]
    assert "maildrop_csrf=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    assert "Secure" in cookie_header


def test_admin_bulk_aliases_requires_csrf():
    client, _session_factory = client_with_db()

    response = client.post(
        "/admin/aliases/bulk",
        data={"count": "2", "length": "8"},
        headers=auth_header(),
    )

    assert response.status_code == 403


def test_admin_bulk_generates_aliases_and_latest_links_with_csrf():
    client, _session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/bulk",
        data={"count": "2", "length": "8", "csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.text.count("@aiprot.space") >= 2
    assert response.text.count("/api/inbox/") >= 2
    assert response.text.count("/latest.txt?token=") >= 2


def test_admin_bulk_form_lists_configured_mail_suffixes():
    client, _session_factory = client_with_db()

    response = client.get("/admin", headers=auth_header())

    assert response.status_code == 200
    assert 'name="mail_domain"' in response.text
    assert '<option value="aiprot.space"' in response.text
    assert '<option value="ssn.aiprot.space"' in response.text
    assert '<option value="sso.aiprot.space"' in response.text
    assert '<option value="wow.aiprot.space"' in response.text
    assert '<option value="oai.aiprot.space"' in response.text
    assert '<option value="why.aiprot.space"' in response.text
    assert '<option value="a.exa.aiprot.space"' in response.text
    assert '<option value="b.exa.aiprot.space"' in response.text


def test_admin_bulk_generates_aliases_for_selected_subdomain():
    client, session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/bulk",
        data={
            "count": "1",
            "length": "8",
            "mail_domain": "ssn.aiprot.space",
            "csrf_token": csrf_token,
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    match = re.search(
        r"([a-z0-9]{8})@ssn\.aiprot\.space https://aiprot\.space/api/inbox/([a-z0-9]{8}--ssn-aiprot-space)/latest\.txt\?token=([A-Za-z0-9_-]+)",
        response.text,
    )
    assert match is not None
    local_part, route_key, token = match.groups()
    assert route_key == f"{local_part}--ssn-aiprot-space"
    with session_factory() as db:
        alias = db.query(Alias).filter_by(email=f"{local_part}@ssn.aiprot.space").one()
        assert alias.prefix == route_key
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": f"{local_part}@ssn.aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    latest = client.get(f"/api/inbox/{route_key}/latest.txt?token={token}")
    assert latest.status_code == 200
    assert f"To: {local_part}@ssn.aiprot.space" in latest.text


def test_admin_bulk_generates_aliases_for_registered_exa_subdomain():
    client, session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/bulk",
        data={
            "count": "1",
            "length": "8",
            "mail_domain": "a.exa.aiprot.space",
            "csrf_token": csrf_token,
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    match = re.search(
        r"([a-z0-9]{8})@a\.exa\.aiprot\.space https://aiprot\.space/api/inbox/([a-z0-9]{8}--a-exa-aiprot-space)/latest\.txt\?token=([A-Za-z0-9_-]+)",
        response.text,
    )
    assert match is not None
    local_part, route_key, token = match.groups()
    assert route_key == f"{local_part}--a-exa-aiprot-space"
    with session_factory() as db:
        alias = db.query(Alias).filter_by(email=f"{local_part}@a.exa.aiprot.space").one()
        assert alias.prefix == route_key
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": f"{local_part}@a.exa.aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    latest = client.get(f"/api/inbox/{route_key}/latest.txt?token={token}")
    assert latest.status_code == 200
    assert f"To: {local_part}@a.exa.aiprot.space" in latest.text


def test_admin_aliases_can_filter_by_mail_domain():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_alias(
            db,
            "alpha--a-exa-aiprot-space",
            "a.exa.aiprot.space",
            email="alpha@a.exa.aiprot.space",
        )
        create_alias(
            db,
            "beta--b-exa-aiprot-space",
            "b.exa.aiprot.space",
            email="beta@b.exa.aiprot.space",
        )

    response = client.get("/admin?mail_domain=a.exa.aiprot.space", headers=auth_header())

    assert response.status_code == 200
    assert "alpha@a.exa.aiprot.space" in response.text
    assert "beta@b.exa.aiprot.space" not in response.text
    assert 'name="mail_domain_filter"' in response.text
    assert '<option value="a.exa.aiprot.space" selected' in response.text


def test_admin_can_register_exa_subdomain_from_ui_and_use_it_for_generation():
    client, session_factory = client_with_db()
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/subdomains",
        data={"csrf_token": csrf_token, "subdomain": "c"},
        headers=auth_header(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    admin = client.get("/admin", headers=auth_header())
    assert '<option value="c.exa.aiprot.space">c.exa.aiprot.space</option>' in admin.text
    csrf_token = csrf_token_from(admin.text)
    generated = client.post(
        "/admin/aliases/bulk",
        data={
            "count": "1",
            "length": "8",
            "mail_domain": "c.exa.aiprot.space",
            "csrf_token": csrf_token,
        },
        headers=auth_header(),
    )

    assert generated.status_code == 200
    match = re.search(
        r"([a-z0-9]{8})@c\.exa\.aiprot\.space https://aiprot\.space/api/inbox/([a-z0-9]{8}--c-exa-aiprot-space)/latest\.txt\?token=([A-Za-z0-9_-]+)",
        generated.text,
    )
    assert match is not None
    local_part, route_key, token = match.groups()
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": f"{local_part}@c.exa.aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    latest = client.get(f"/api/inbox/{route_key}/latest.txt?token={token}")
    assert latest.status_code == 200
    assert f"To: {local_part}@c.exa.aiprot.space" in latest.text
    with session_factory() as db:
        alias = db.query(Alias).filter_by(email=f"{local_part}@c.exa.aiprot.space").one()
        assert alias.prefix == route_key


def test_admin_rejects_invalid_registered_exa_subdomain_names():
    client, _session_factory = client_with_db()
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/subdomains",
        data={"csrf_token": csrf_token, "subdomain": "bad/name"},
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid subdomain"


def test_admin_refuses_to_delete_registered_exa_subdomain_with_aliases():
    client, session_factory = client_with_db()
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)
    client.post(
        "/admin/subdomains",
        data={"csrf_token": csrf_token, "subdomain": "c"},
        headers=auth_header(),
        follow_redirects=False,
    )
    with session_factory() as db:
        create_alias(
            db,
            "alpha--c-exa-aiprot-space",
            "c.exa.aiprot.space",
            email="alpha@c.exa.aiprot.space",
        )
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)
    with session_factory() as db:
        subdomain_id = db.query(RegisteredSubdomain).filter_by(domain="c.exa.aiprot.space").one().id

    response = client.post(
        f"/admin/subdomains/{subdomain_id}/delete",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "subdomain has aliases"


def test_admin_syncs_openai_txt_subdomains_from_spaceship():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "type": "TXT",
                        "name": "urxg.exa",
                        "value": "openai-domain-verification=dv-123",
                    },
                    {
                        "type": "TXT",
                        "name": "ignored.exa",
                        "value": "not-openai",
                    },
                ],
                "total": 2,
            },
        )

    app_settings = Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        mail_domains="aiprot.space",
        database_url="sqlite+pysqlite:///:memory:",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
        spaceship_api_key="key",
        spaceship_api_secret="secret",
        spaceship_dns_domain="aiprot.space",
    )
    client, session_factory = client_with_db(
        app_settings=app_settings,
        spaceship_transport=httpx.MockTransport(handler),
    )
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/subdomains/sync-spaceship",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "新增 1 个" in response.text
    assert "urxg.exa.aiprot.space" in response.text
    with session_factory() as db:
        stored = db.query(RegisteredSubdomain).filter_by(domain="urxg.exa.aiprot.space").one()
        assert stored.domain == "urxg.exa.aiprot.space"
    assert requests[0].headers["X-API-Key"] == "key"
    assert requests[0].headers["X-API-Secret"] == "secret"


def test_admin_spaceship_sync_requires_api_credentials():
    client, _session_factory = client_with_db()
    form = client.get("/admin/subdomains", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/subdomains/sync-spaceship",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "spaceship api is not configured"


def test_admin_bulk_rejects_unconfigured_mail_suffix():
    client, _session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/bulk",
        data={
            "count": "1",
            "length": "8",
            "mail_domain": "evil.example",
            "csrf_token": csrf_token,
        },
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported mail domain"


def test_admin_can_rotate_existing_alias_token_and_show_new_api_link():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _alias, old_token = create_alias(db, "alpha", "aiprot.space")
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    old_latest = f"/api/inbox/alpha/latest.txt?token={old_token}"
    assert client.get(old_latest).status_code == 200
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/alpha/token",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "alpha@aiprot.space" in response.text
    assert "token-hidden-after-creation" in response.text
    match = re.search(r"https://aiprot\.space/api/inbox/alpha/latest\.txt\?token=([A-Za-z0-9_-]+)", response.text)
    assert match is not None
    new_token = match.group(1)
    assert new_token != old_token
    assert client.get(old_latest).status_code == 403
    assert client.get(f"/api/inbox/alpha/latest.txt?token={new_token}").status_code == 200


def test_admin_exports_selected_aliases_and_rotates_only_selected_tokens():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _alpha, old_alpha_token = create_alias(db, "alpha", "aiprot.space")
        _beta, old_beta_token = create_alias(db, "beta", "aiprot.space")
    for prefix in ("alpha", "beta"):
        client.post(
            "/internal/ingest",
            content=RAW,
            headers={
                "X-Envelope-Recipient": f"{prefix}@aiprot.space",
                "X-Ingest-Token": "ingest-secret",
            },
        )
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/export",
        data={"csrf_token": csrf_token, "prefixes": ["alpha"]},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "attachment; filename=maildrop-alias-links.txt" in response.headers["content-disposition"]
    assert "alpha@aiprot.space https://aiprot.space/api/inbox/alpha/latest.txt?token=" in response.text
    assert "beta@aiprot.space" not in response.text
    new_alpha_token = exported_token_for(response.text, "alpha")
    assert new_alpha_token != old_alpha_token
    assert client.get(f"/api/inbox/alpha/latest.txt?token={old_alpha_token}").status_code == 403
    assert client.get(f"/api/inbox/alpha/latest.txt?token={new_alpha_token}").status_code == 200
    assert client.get(f"/api/inbox/beta/latest.txt?token={old_beta_token}").status_code == 200
    with session_factory() as db:
        alpha = db.query(Alias).filter_by(prefix="alpha").one()
        beta = db.query(Alias).filter_by(prefix="beta").one()
        assert alpha.exported_at is not None
        assert beta.exported_at is None


def test_admin_exports_all_aliases_and_rotates_all_tokens():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _alpha, old_alpha_token = create_alias(db, "alpha", "aiprot.space")
        _beta, old_beta_token = create_alias(db, "beta", "aiprot.space")
    for prefix in ("alpha", "beta"):
        client.post(
            "/internal/ingest",
            content=RAW,
            headers={
                "X-Envelope-Recipient": f"{prefix}@aiprot.space",
                "X-Ingest-Token": "ingest-secret",
            },
        )
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/export",
        data={"csrf_token": csrf_token, "scope": "all"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    alpha_token = exported_token_for(response.text, "alpha")
    beta_token = exported_token_for(response.text, "beta")
    assert alpha_token != old_alpha_token
    assert beta_token != old_beta_token
    assert client.get(f"/api/inbox/alpha/latest.txt?token={old_alpha_token}").status_code == 403
    assert client.get(f"/api/inbox/beta/latest.txt?token={old_beta_token}").status_code == 403
    assert client.get(f"/api/inbox/alpha/latest.txt?token={alpha_token}").status_code == 200
    assert client.get(f"/api/inbox/beta/latest.txt?token={beta_token}").status_code == 200


def test_admin_export_all_excludes_deleted_aliases():
    client, session_factory = client_with_db()
    with session_factory() as db:
        _active, _active_token = create_alias(db, "active", "aiprot.space")
        deleted, deleted_token = create_alias(db, "deleted", "aiprot.space")
        deleted.enabled = False
        deleted.deleted_at = datetime.now(timezone.utc)
        db.commit()
    for prefix in ("active", "deleted"):
        client.post(
            "/internal/ingest",
            content=RAW,
            headers={
                "X-Envelope-Recipient": f"{prefix}@aiprot.space",
                "X-Ingest-Token": "ingest-secret",
            },
        )
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/export",
        data={"csrf_token": csrf_token, "scope": "all"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "active@aiprot.space" in response.text
    assert "deleted@aiprot.space" not in response.text
    assert client.get(f"/api/inbox/deleted/latest.txt?token={deleted_token}").status_code == 403
    with session_factory() as db:
        deleted = db.query(Alias).filter_by(prefix="deleted").one()
        assert deleted.exported_at is None


def test_admin_export_requires_selection_or_all_scope():
    client, _session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/export",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "select aliases or export all"


def test_unassigned_page_offers_register_and_import_action():
    client, _session_factory = client_with_db()
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "unreg@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    response = client.get("/admin/unassigned", headers=auth_header())

    assert response.status_code == 200
    assert "unreg@aiprot.space" in response.text
    assert "登记并导入" in response.text
    assert "/admin/unassigned/" in response.text
    assert "/register-import" in response.text


def test_admin_registers_unassigned_message_and_imports_manager_inbox():
    client, session_factory = client_with_db()
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "unreg@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    with session_factory() as db:
        unassigned_id = db.query(UnassignedMessage).filter_by(recipient="unreg@aiprot.space").one().id
    form = client.get("/admin/unassigned", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/admin/unassigned/{unassigned_id}/register-import",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "收件管理器" in response.text
    assert "unreg@aiprot.space" in response.text
    assert "已登记并导入 unreg@aiprot.space" in response.text
    with session_factory() as db:
        alias = db.query(Alias).filter_by(prefix="unreg").one()
        managed = db.query(ManagedInbox).filter_by(email="unreg@aiprot.space").one()
        assert alias.enabled is True
        assert alias.deleted_at is None
        assert alias.message_count == 1
        assert db.query(Message).filter_by(alias_id=alias.id).count() == 1
        assert db.query(UnassignedMessage).filter_by(recipient="unreg@aiprot.space").count() == 0
        assert managed.status == "pending"
        assert managed.api_url.startswith("https://aiprot.space/api/inbox/unreg/latest.txt?token=")

    parsed = urlparse(managed.api_url)
    latest = client.get(f"{parsed.path}?{parsed.query}")
    assert latest.status_code == 200
    assert "Hello" in latest.text
    assert "Body" in latest.text


def test_admin_registers_unassigned_subdomain_message_with_route_key():
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool

    from maildrop.app import create_app
    from maildrop.config import Settings
    from maildrop.db import create_engine_from_url, create_schema, make_session_factory

    engine = create_engine_from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    session_factory = make_session_factory(engine)
    app = create_app(
        Settings(
            app_base_url="https://aiprot.space",
            mail_domain="aiprot.space",
            mail_domains="aiprot.space,ssn.aiprot.space",
            database_url="sqlite+pysqlite:///:memory:",
            admin_username="admin",
            admin_password="admin-secret",
            ingest_token="ingest-secret",
        ),
        session_factory=session_factory,
    )
    client = TestClient(app, base_url="https://testserver")
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@ssn.aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    with session_factory() as db:
        unassigned_id = db.query(UnassignedMessage).filter_by(recipient="alpha@ssn.aiprot.space").one().id
    form = client.get("/admin/unassigned", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/admin/unassigned/{unassigned_id}/register-import",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        alias = db.query(Alias).filter_by(email="alpha@ssn.aiprot.space").one()
        managed = db.query(ManagedInbox).filter_by(email="alpha@ssn.aiprot.space").one()
        assert alias.prefix == "alpha--ssn-aiprot-space"
        assert managed.api_url.startswith(
            "https://aiprot.space/api/inbox/alpha--ssn-aiprot-space/latest.txt?token="
        )

    parsed = urlparse(managed.api_url)
    latest = client.get(f"{parsed.path}?{parsed.query}")
    assert latest.status_code == 200
    assert "To: alpha@ssn.aiprot.space" in latest.text


def test_register_unassigned_requires_csrf():
    client, session_factory = client_with_db()
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "csrfcase@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )
    with session_factory() as db:
        unassigned_id = db.query(UnassignedMessage).filter_by(recipient="csrfcase@aiprot.space").one().id

    response = client.post(
        f"/admin/unassigned/{unassigned_id}/register-import",
        headers=auth_header(),
    )

    assert response.status_code == 403


def test_admin_category_filters_aliases_by_export_and_delete_state():
    client, session_factory = client_with_db()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        create_alias(db, "fresh", "aiprot.space")
        exported, _ = create_alias(db, "exported", "aiprot.space")
        deleted, _ = create_alias(db, "deleted", "aiprot.space")
        exported.exported_at = now
        deleted.enabled = False
        deleted.deleted_at = now
        db.commit()

    unexported = client.get("/admin?category=unexported", headers=auth_header())
    exported_response = client.get("/admin?category=exported", headers=auth_header())
    deleted_response = client.get("/admin?category=deleted", headers=auth_header())
    all_response = client.get("/admin?category=all", headers=auth_header())

    assert unexported.status_code == 200
    assert "fresh@aiprot.space" in unexported.text
    assert "exported@aiprot.space" not in unexported.text
    assert "deleted@aiprot.space" not in unexported.text
    assert "exported@aiprot.space" in exported_response.text
    assert "fresh@aiprot.space" not in exported_response.text
    assert "deleted@aiprot.space" in deleted_response.text
    assert "fresh@aiprot.space" not in deleted_response.text
    assert "fresh@aiprot.space" in all_response.text
    assert "exported@aiprot.space" in all_response.text
    assert "deleted@aiprot.space" in all_response.text


def test_admin_can_soft_delete_alias_and_preserve_messages():
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
    assert client.get(f"/api/inbox/alpha/latest.txt?token={token}").status_code == 200
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/alpha/delete",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "alpha@aiprot.space" in response.text
    assert "已删除" in response.text
    assert client.get(f"/api/inbox/alpha/latest.txt?token={token}").status_code == 403
    with session_factory() as db:
        alias = db.query(Alias).filter_by(prefix="alpha").one()
        assert alias.deleted_at is not None
        assert alias.enabled is False
        assert db.query(Message).filter_by(alias_id=alias.id).count() == 1
    deleted_page = client.get("/admin?category=deleted", headers=auth_header())
    assert "alpha@aiprot.space" in deleted_page.text


def test_admin_bulk_soft_deletes_selected_aliases():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_alias(db, "alpha", "aiprot.space")
        create_alias(db, "beta", "aiprot.space")
        create_alias(db, "gamma", "aiprot.space")
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/delete",
        data={"csrf_token": csrf_token, "prefixes": ["alpha", "gamma"]},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        alpha = db.query(Alias).filter_by(prefix="alpha").one()
        beta = db.query(Alias).filter_by(prefix="beta").one()
        gamma = db.query(Alias).filter_by(prefix="gamma").one()
        assert alpha.deleted_at is not None
        assert beta.deleted_at is None
        assert gamma.deleted_at is not None
        assert alpha.enabled is False
        assert beta.enabled is True
        assert gamma.enabled is False


def test_admin_delete_requires_selection():
    client, _session_factory = client_with_db()
    form = client.get("/admin", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/admin/aliases/delete",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "select aliases to delete"


def test_admin_search_filters_aliases():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_alias(db, "alpha", "aiprot.space")
        create_alias(db, "beta", "aiprot.space")

    response = client.get("/admin?q=alp", headers=auth_header())

    assert response.status_code == 200
    assert "alpha@aiprot.space" in response.text
    assert "beta@aiprot.space" not in response.text


def test_admin_alias_list_is_paginated_for_large_alias_sets():
    client, session_factory = client_with_db()
    with session_factory() as db:
        for index in range(205):
            create_alias(db, f"bulk{index:03d}", "aiprot.space")

    response = client.get("/admin?page=2&page_size=100", headers=auth_header())

    assert response.status_code == 200
    assert "共 205 个结果，第 2 / 3 页" in response.text
    assert response.text.count('name="prefixes"') == 100
    assert "page=1&page_size=100" in response.text
    assert "page=3&page_size=100" in response.text


def test_admin_alias_search_pagination_preserves_query():
    client, session_factory = client_with_db()
    with session_factory() as db:
        for index in range(75):
            create_alias(db, f"team{index:03d}", "aiprot.space")
        create_alias(db, "other", "aiprot.space")

    response = client.get("/admin?q=team&page=2&page_size=50", headers=auth_header())

    assert response.status_code == 200
    assert "共 75 个结果，第 2 / 2 页" in response.text
    assert "other@aiprot.space" not in response.text
    assert "q=team&page=1&page_size=50" in response.text


def test_admin_unassigned_page_shows_unknown_mail():
    client, _session_factory = client_with_db()
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "unknown@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    response = client.get("/admin/unassigned", headers=auth_header())

    assert response.status_code == 200
    assert "未登记邮件" in response.text
    assert "unknown@aiprot.space" in response.text
    assert "Hello" in response.text


def test_admin_unassigned_page_is_paginated():
    client, session_factory = client_with_db()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add_all(
            UnassignedMessage(
                recipient=f"unknown{index:03d}@aiprot.space",
                sender="sender@example.net",
                subject=f"Unknown {index:03d}",
                text_body="Body",
                html_body="",
                raw_mime=b"",
                headers_json={},
                reason="alias_not_registered",
                received_at=now - timedelta(minutes=index),
            )
            for index in range(75)
        )
        db.commit()

    response = client.get("/admin/unassigned?page=2&page_size=50", headers=auth_header())

    assert response.status_code == 200
    assert "共 75 封，第 2 / 2 页" in response.text
    assert "unknown050@aiprot.space" in response.text
    assert "unknown049@aiprot.space" not in response.text
    assert "page=1&page_size=50" in response.text


def test_admin_alias_messages_page_shows_recent_mail():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_alias(db, "alpha", "aiprot.space")
    client.post(
        "/internal/ingest",
        content=RAW,
        headers={
            "X-Envelope-Recipient": "alpha@aiprot.space",
            "X-Ingest-Token": "ingest-secret",
        },
    )

    response = client.get("/admin/aliases/alpha/messages", headers=auth_header())

    assert response.status_code == 200
    assert "alpha@aiprot.space" in response.text
    assert "Hello" in response.text
    assert "sender@example.com" in response.text


def test_admin_alias_messages_page_is_paginated():
    client, session_factory = client_with_db()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        alias, _token = create_alias(db, "alpha", "aiprot.space")
        db.add_all(
            Message(
                alias_id=alias.id,
                recipient=alias.email,
                sender="sender@example.net",
                subject=f"Message {index:03d}",
                text_body="Body",
                html_body="",
                raw_mime=b"",
                headers_json={},
                received_at=now - timedelta(minutes=index),
            )
            for index in range(75)
        )
        alias.message_count = 75
        alias.last_message_at = now
        db.commit()

    response = client.get(
        "/admin/aliases/alpha/messages?page=2&page_size=50",
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "最近邮件，共 75 封，第 2 / 2 页" in response.text
    assert "Message 050" in response.text
    assert "Message 049" not in response.text
    assert "page=1&page_size=50" in response.text
