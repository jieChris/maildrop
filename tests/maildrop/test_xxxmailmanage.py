from datetime import datetime, timezone

import pytest

from maildrop.models import ManagedInbox
from tests.maildrop.test_admin import auth_header, csrf_token_from
from tests.maildrop.test_api import client_with_db


def create_managed(db, email: str, status: str = "pending", api_url: str | None = None):
    now = datetime.now(timezone.utc)
    item = ManagedInbox(
        email=email,
        api_url=api_url or f"https://example.test/{email}/latest.txt",
        status=status,
        note="",
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


CHATGPT_PREVIEW = """From: noreply@tm.openai.com
To: wnyz41w0r5fa@aiprot.space
Subject: 你的 ChatGPT 临时验证码
Received: 2026-06-12T16:02:24.207599+00:00

你的 ChatGPT 临时验证码
输入此临时验证码以继续：
306268
如果并非你本人尝试创建 ChatGPT 帐户，请忽略此电子邮件。
谨致问候
ChatGPT 团队
"""


def test_xxxmailmanage_requires_basic_auth():
    client, _session_factory = client_with_db()

    response = client.get("/xxxmailmanage")

    assert response.status_code == 401


def test_xxxmailmanage_page_renders_manager_controls():
    client, _session_factory = client_with_db()

    response = client.get("/xxxmailmanage", headers=auth_header())

    assert response.status_code == 200
    assert "收件管理器" in response.text
    assert "批量导入" in response.text
    assert "标记已消耗" in response.text


def test_xxxmailmanage_renders_collapsible_latest_preview_and_copyable_code():
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space", api_url="https://example.test/alpha/latest.txt")
        item.last_preview = CHATGPT_PREVIEW
        db.commit()

    response = client.get("/xxxmailmanage", headers=auth_header())

    assert response.status_code == 200
    assert 'data-toggle-detail="true"' in response.text
    assert "展开" in response.text
    assert "最新内容" in response.text
    assert 'class="code-chip"' in response.text
    assert 'data-copy="306268"' in response.text
    assert ">306268</button>" in response.text
    assert 'class="manager-code-slot"' in response.text
    assert 'class="manager-url"' not in response.text
    assert "API链接" in response.text
    assert 'data-copy="https://example.test/alpha/latest.txt"' in response.text
    assert 'data-async-action="refresh"' in response.text
    assert 'data-async-action="status"' in response.text
    assert 'data-async-action="delete"' in response.text


def test_xxxmailmanage_import_requires_csrf():
    client, _session_factory = client_with_db()

    response = client.post(
        "/xxxmailmanage/import",
        data={"rows": "alpha@aiprot.space https://example.test/latest.txt"},
        headers=auth_header(),
    )

    assert response.status_code == 403


def test_xxxmailmanage_imports_rows_and_shows_summary():
    client, session_factory = client_with_db()
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/xxxmailmanage/import",
        data={
            "csrf_token": csrf_token,
            "rows": "alpha@aiprot.space https://example.test/alpha/latest.txt\ninvalid-row",
        },
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert "导入完成：新增 1，更新 0，无效 1" in response.text
    assert "alpha@aiprot.space" in response.text
    with session_factory() as db:
        item = db.query(ManagedInbox).filter_by(email="alpha@aiprot.space").one()
        assert item.status == "pending"


def test_xxxmailmanage_filters_by_status_and_search():
    client, session_factory = client_with_db()
    with session_factory() as db:
        create_managed(db, "alpha@aiprot.space", "pending")
        create_managed(db, "beta@aiprot.space", "used")
        create_managed(db, "gamma@aiprot.space", "error")

    response = client.get("/xxxmailmanage?status=used&q=bet", headers=auth_header())

    assert response.status_code == 200
    assert "beta@aiprot.space" in response.text
    assert "alpha@aiprot.space" not in response.text
    assert "gamma@aiprot.space" not in response.text


def test_xxxmailmanage_bulk_status_updates_selected_rows():
    client, session_factory = client_with_db()
    with session_factory() as db:
        alpha = create_managed(db, "alpha@aiprot.space")
        beta = create_managed(db, "beta@aiprot.space")
        alpha_id = alpha.id
        beta_id = beta.id
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        "/xxxmailmanage/status",
        data={"csrf_token": csrf_token, "ids": [str(alpha_id)], "status": "used"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        assert db.get(ManagedInbox, alpha_id).status == "used"
        assert db.get(ManagedInbox, beta_id).status == "pending"


def test_xxxmailmanage_status_json_updates_single_row_without_full_page():
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space")
        item_id = item.id
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item_id}/status.json",
        data={"csrf_token": csrf_token, "status": "used"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["item"]["status"] == "used"
    assert response.json()["item"]["status_label"] == "已消耗"
    with session_factory() as db:
        assert db.get(ManagedInbox, item_id).status == "used"


def test_xxxmailmanage_deletes_single_row():
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space")
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item.id}/delete",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        assert db.get(ManagedInbox, item.id) is None


def test_xxxmailmanage_delete_json_removes_single_row_without_full_page():
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space")
        item_id = item.id
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item_id}/delete.json",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["item_id"] == item_id
    assert response.json()["stats"]["total"] == 0
    with session_factory() as db:
        assert db.get(ManagedInbox, item_id) is None


def test_xxxmailmanage_refresh_stores_preview(monkeypatch):
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space", api_url="https://example.test/latest.txt")

    class FakeResponse:
        status_code = 200
        text = "From: sender@example.test\n\nhello"

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url):
            assert url == "https://example.test/latest.txt"
            return FakeResponse()

    import maildrop.app as app_module

    monkeypatch.setattr(app_module.httpx, "Client", FakeClient)
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item.id}/refresh",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        refreshed = db.get(ManagedInbox, item.id)
        assert refreshed.last_preview == "From: sender@example.test\n\nhello"
        assert refreshed.last_error is None


def test_xxxmailmanage_refresh_json_returns_preview_and_codes(monkeypatch):
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space", api_url="https://example.test/latest.txt")
        item_id = item.id

    class FakeResponse:
        status_code = 200
        text = CHATGPT_PREVIEW

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url):
            assert url == "https://example.test/latest.txt"
            return FakeResponse()

    import maildrop.app as app_module

    monkeypatch.setattr(app_module.httpx, "Client", FakeClient)
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item_id}/refresh.json",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    payload = response.json()["item"]
    assert payload["last_preview"] == CHATGPT_PREVIEW
    assert payload["last_error"] is None
    assert payload["codes"] == ["306268"]
    assert payload["api_url"] == "https://example.test/latest.txt"


def test_xxxmailmanage_refresh_marks_error_on_failure(monkeypatch):
    client, session_factory = client_with_db()
    with session_factory() as db:
        item = create_managed(db, "alpha@aiprot.space", api_url="https://example.test/latest.txt")

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url):
            raise TimeoutError("blocked")

    import maildrop.app as app_module

    monkeypatch.setattr(app_module.httpx, "Client", FakeClient)
    form = client.get("/xxxmailmanage", headers=auth_header())
    csrf_token = csrf_token_from(form.text)

    response = client.post(
        f"/xxxmailmanage/{item.id}/refresh",
        data={"csrf_token": csrf_token},
        headers=auth_header(),
    )

    assert response.status_code == 200
    with session_factory() as db:
        refreshed = db.get(ManagedInbox, item.id)
        assert refreshed.status == "error"
        assert "blocked" in refreshed.last_error
