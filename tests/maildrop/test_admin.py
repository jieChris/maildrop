from base64 import b64encode
from datetime import datetime, timedelta, timezone
import re

from maildrop.models import Message, UnassignedMessage
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
