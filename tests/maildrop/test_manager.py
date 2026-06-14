from datetime import datetime, timezone

from maildrop.manager import (
    VALID_MANAGER_STATUSES,
    bulk_update_status,
    delete_managed_inbox,
    extract_verification_codes,
    import_managed_inboxes,
    manager_stats,
    parse_import_rows,
)
from maildrop.models import ManagedInbox


def test_parse_import_rows_supports_common_separators():
    rows = parse_import_rows(
        """
        alpha@aiprot.space https://aiprot.space/api/inbox/alpha/latest.txt?token=a
        beta@aiprot.space----https://aiprot.space/api/inbox/beta/latest.txt?token=b
        gamma@aiprot.space\thttps://aiprot.space/api/inbox/gamma/latest.txt?token=c
        delta@aiprot.space,https://aiprot.space/api/inbox/delta/latest.txt?token=d
        bad-row-without-url
        """
    )

    assert [(row.email, row.api_url) for row in rows.valid] == [
        ("alpha@aiprot.space", "https://aiprot.space/api/inbox/alpha/latest.txt?token=a"),
        ("beta@aiprot.space", "https://aiprot.space/api/inbox/beta/latest.txt?token=b"),
        ("gamma@aiprot.space", "https://aiprot.space/api/inbox/gamma/latest.txt?token=c"),
        ("delta@aiprot.space", "https://aiprot.space/api/inbox/delta/latest.txt?token=d"),
    ]
    assert rows.invalid_count == 1


def test_extract_verification_codes_from_chatgpt_message():
    preview = """From: noreply@tm.openai.com
To: wnyz41w0r5fa@aiprot.space
Subject: 你的 ChatGPT 临时验证码
Received: 2026-06-12T16:02:24.207599+00:00

你的 ChatGPT 临时验证码
输入此临时验证码以继续：
306268
如果并非你本人尝试创建 ChatGPT 帐户，请忽略此电子邮件。
谨致问候
ChatGPT 团队
ChatGPT
帮助中心
"""

    assert extract_verification_codes(preview) == ["306268"]


def test_extract_verification_codes_ignores_dates_and_times_without_context():
    preview = """From: service@example.test
Received: 2026-06-12T16:02:24.207599+00:00

登录时间 2026-06-12 16:02
没有验证码内容
"""

    assert extract_verification_codes(preview) == []


def test_import_managed_inboxes_upserts_without_resetting_status_or_note(db_session):
    existing = ManagedInbox(
        email="alpha@aiprot.space",
        api_url="https://old.example/latest.txt",
        status="used",
        note="keep note",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.commit()

    result = import_managed_inboxes(
        db_session,
        """
        ALPHA@aiprot.space https://new.example/latest.txt
        beta@aiprot.space https://beta.example/latest.txt
        invalid-row
        """,
    )

    assert result == {"created": 1, "updated": 1, "invalid": 1}
    alpha = db_session.query(ManagedInbox).filter_by(email="alpha@aiprot.space").one()
    beta = db_session.query(ManagedInbox).filter_by(email="beta@aiprot.space").one()
    assert alpha.api_url == "https://new.example/latest.txt"
    assert alpha.status == "used"
    assert alpha.note == "keep note"
    assert beta.status == "pending"
    assert beta.note == ""


def test_manager_stats_counts_statuses(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ManagedInbox(email="a@example.test", api_url="https://a", status="pending", note="", created_at=now, updated_at=now),
            ManagedInbox(email="b@example.test", api_url="https://b", status="used", note="", created_at=now, updated_at=now),
            ManagedInbox(email="c@example.test", api_url="https://c", status="error", note="", created_at=now, updated_at=now),
        ]
    )
    db_session.commit()

    assert manager_stats(db_session) == {"total": 3, "pending": 1, "used": 1, "error": 1}


def test_bulk_update_status_and_delete_managed_inbox(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ManagedInbox(email="a@example.test", api_url="https://a", status="pending", note="", created_at=now, updated_at=now),
            ManagedInbox(email="b@example.test", api_url="https://b", status="pending", note="", created_at=now, updated_at=now),
            ManagedInbox(email="c@example.test", api_url="https://c", status="pending", note="", created_at=now, updated_at=now),
        ]
    )
    db_session.commit()
    ids = [item.id for item in db_session.query(ManagedInbox).order_by(ManagedInbox.email).all()]

    assert bulk_update_status(db_session, ids[:2], "used") == 2
    assert db_session.get(ManagedInbox, ids[0]).status == "used"
    assert db_session.get(ManagedInbox, ids[1]).status == "used"
    assert db_session.get(ManagedInbox, ids[2]).status == "pending"
    assert delete_managed_inbox(db_session, ids[0]) is True
    assert db_session.get(ManagedInbox, ids[0]) is None


def test_bulk_update_rejects_invalid_status(db_session):
    assert VALID_MANAGER_STATUSES == {"pending", "used", "error"}
    try:
        bulk_update_status(db_session, [1], "other")
    except ValueError as exc:
        assert str(exc) == "invalid manager status"
    else:
        raise AssertionError("expected invalid status")
