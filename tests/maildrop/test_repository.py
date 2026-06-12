from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from maildrop.mailparse import ParsedMessage
from maildrop.models import Alias, Message, UnassignedMessage
from maildrop.repository import (
    cleanup_old_messages,
    create_alias,
    generate_aliases,
    ingest_parsed_message,
    latest_message_for_alias,
)
from maildrop.security import verify_token


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


def message_for(alias: Alias, subject: str, received_at: datetime) -> Message:
    return Message(
        alias_id=alias.id,
        recipient=alias.email,
        sender="sender@example.com",
        subject=subject,
        received_at=received_at,
        text_body=subject,
        html_body="",
        raw_mime=f"{subject} raw",
        headers_json={},
    )


def unassigned(subject: str, received_at: datetime, reason: str) -> UnassignedMessage:
    return UnassignedMessage(
        recipient=f"{subject.lower().replace(' ', '-')}@aiprot.space",
        sender="sender@example.com",
        subject=subject,
        received_at=received_at,
        text_body=subject,
        html_body="",
        raw_mime=f"{subject} raw",
        headers_json={},
        reason=reason,
    )


def test_create_alias_stores_hash_and_returns_plain_token(db_session):
    alias, token = create_alias(db_session, "alpha", "aiprot.space")

    assert alias.email == "alpha@aiprot.space"
    assert token
    assert alias.api_token_hash != token
    assert verify_token(token, alias.api_token_hash)


def test_ingest_registered_alias_stores_message(db_session):
    alias, _ = create_alias(db_session, "alpha", "aiprot.space")

    result = ingest_parsed_message(
        db_session,
        parsed("alpha@aiprot.space"),
        expected_domain="aiprot.space",
    )

    latest = latest_message_for_alias(db_session, alias)
    assert result == "assigned"
    assert latest is not None
    assert latest.subject == "Subject"
    assert alias.message_count == 1


def test_ingest_unknown_alias_goes_to_unassigned(db_session):
    result = ingest_parsed_message(
        db_session,
        parsed("unknown@aiprot.space"),
        expected_domain="aiprot.space",
    )

    stored = db_session.query(UnassignedMessage).one()
    assert result == "unassigned"
    assert stored.recipient == "unknown@aiprot.space"
    assert stored.reason == "alias_not_registered"


def test_ingest_other_domain_goes_to_unassigned_without_alias_match(db_session):
    create_alias(db_session, "alpha", "aiprot.space")

    result = ingest_parsed_message(
        db_session,
        parsed("alpha@example.net"),
        expected_domain="aiprot.space",
    )

    stored = db_session.query(UnassignedMessage).one()
    assert result == "unassigned"
    assert stored.recipient == "alpha@example.net"
    assert stored.reason == "domain_not_allowed"
    assert latest_message_for_alias(db_session, db_session.query(Alias).one()) is None


def test_ingest_disabled_alias_goes_to_unassigned(db_session):
    alias, _ = create_alias(db_session, "alpha", "aiprot.space")
    alias.enabled = False
    db_session.commit()

    result = ingest_parsed_message(
        db_session,
        parsed("alpha@aiprot.space"),
        expected_domain="aiprot.space",
    )

    stored = db_session.query(UnassignedMessage).one()
    assert result == "unassigned"
    assert stored.recipient == "alpha@aiprot.space"
    assert stored.reason == "alias_disabled"
    assert latest_message_for_alias(db_session, alias) is None


def test_ingest_deleted_alias_goes_to_unassigned(db_session):
    alias, _ = create_alias(db_session, "alpha", "aiprot.space")
    alias.enabled = False
    alias.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    result = ingest_parsed_message(
        db_session,
        parsed("alpha@aiprot.space"),
        expected_domain="aiprot.space",
    )

    stored = db_session.query(UnassignedMessage).one()
    assert result == "unassigned"
    assert stored.recipient == "alpha@aiprot.space"
    assert stored.reason == "alias_deleted"
    assert latest_message_for_alias(db_session, alias) is None


def test_generate_aliases_creates_requested_count_with_single_commit(db_session):
    commits = 0

    @event.listens_for(db_session, "after_commit")
    def count_commit(session):
        nonlocal commits
        commits += 1

    created = generate_aliases(db_session, "aiprot.space", count=3, length=10)

    assert len(created) == 3
    assert db_session.query(Alias).count() == 3
    assert commits == 1
    assert all(item[0].email.endswith("@aiprot.space") for item in created)
    assert all(verify_token(token, alias.api_token_hash) for alias, token in created)


def test_cleanup_old_messages_removes_expired_rows_and_recomputes_alias_stats(db_session):
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    alias, _ = create_alias(db_session, "alpha", "aiprot.space")
    old_message = Message(
        alias_id=alias.id,
        recipient="alpha@aiprot.space",
        sender="sender@example.com",
        subject="Old",
        received_at=now - timedelta(days=181),
        text_body="old",
        html_body="",
        raw_mime="old raw",
        headers_json={},
    )
    recent_message = Message(
        alias_id=alias.id,
        recipient="alpha@aiprot.space",
        sender="sender@example.com",
        subject="Recent",
        received_at=now - timedelta(days=2),
        text_body="recent",
        html_body="",
        raw_mime="recent raw",
        headers_json={},
    )
    old_unassigned = UnassignedMessage(
        recipient="unknown@aiprot.space",
        sender="sender@example.com",
        subject="Old Unknown",
        received_at=now - timedelta(days=31),
        text_body="old unknown",
        html_body="",
        raw_mime="old unknown raw",
        headers_json={},
        reason="alias_not_registered",
    )
    recent_unassigned = UnassignedMessage(
        recipient="new@aiprot.space",
        sender="sender@example.com",
        subject="Recent Unknown",
        received_at=now - timedelta(days=1),
        text_body="recent unknown",
        html_body="",
        raw_mime="recent unknown raw",
        headers_json={},
        reason="alias_not_registered",
    )
    db_session.add_all([old_message, recent_message, old_unassigned, recent_unassigned])
    alias.message_count = 2
    alias.last_message_at = old_message.received_at
    db_session.commit()

    result = cleanup_old_messages(
        db_session,
        message_retention_days=180,
        unassigned_retention_days=30,
        now=now,
    )

    assert result == {"messages_deleted": 1, "unassigned_deleted": 1, "aliases_updated": 1}
    assert [message.subject for message in db_session.query(Message).all()] == ["Recent"]
    assert [message.subject for message in db_session.query(UnassignedMessage).all()] == [
        "Recent Unknown"
    ]
    refreshed_alias = db_session.get(Alias, alias.id)
    assert refreshed_alias.message_count == 1
    assert refreshed_alias.last_message_at == recent_message.received_at


def test_cleanup_keeps_messages_exactly_on_retention_cutoff(db_session):
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    alias, _ = create_alias(db_session, "edge", "aiprot.space")
    cutoff_message = message_for(alias, "Message Cutoff", now - timedelta(days=180))
    expired_message = message_for(
        alias,
        "Message Expired",
        now - timedelta(days=180, seconds=1),
    )
    cutoff_unassigned = unassigned(
        "Unassigned Cutoff",
        now - timedelta(days=30),
        "domain_not_allowed",
    )
    expired_unassigned = unassigned(
        "Unassigned Expired",
        now - timedelta(days=30, seconds=1),
        "alias_disabled",
    )
    db_session.add_all([cutoff_message, expired_message, cutoff_unassigned, expired_unassigned])
    alias.message_count = 2
    alias.last_message_at = cutoff_message.received_at
    db_session.commit()

    result = cleanup_old_messages(
        db_session,
        message_retention_days=180,
        unassigned_retention_days=30,
        now=now,
    )

    assert result["messages_deleted"] == 1
    assert result["unassigned_deleted"] == 1
    assert [message.subject for message in db_session.query(Message).all()] == ["Message Cutoff"]
    assert [message.subject for message in db_session.query(UnassignedMessage).all()] == [
        "Unassigned Cutoff"
    ]


def test_cleanup_sets_alias_stats_to_zero_when_all_messages_expire(db_session):
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    alias, _ = create_alias(db_session, "empty", "aiprot.space")
    old_message = message_for(alias, "Only Old", now - timedelta(days=181))
    db_session.add(old_message)
    alias.message_count = 1
    alias.last_message_at = old_message.received_at
    db_session.commit()

    result = cleanup_old_messages(
        db_session,
        message_retention_days=180,
        unassigned_retention_days=30,
        now=now,
    )

    refreshed_alias = db_session.get(Alias, alias.id)
    assert result == {"messages_deleted": 1, "unassigned_deleted": 0, "aliases_updated": 1}
    assert refreshed_alias.message_count == 0
    assert refreshed_alias.last_message_at is None


def test_cleanup_dry_run_counts_without_deleting_or_updating_stats(db_session):
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    alias, _ = create_alias(db_session, "dry", "aiprot.space")
    old_message = message_for(alias, "Dry Old", now - timedelta(days=181))
    old_unassigned = unassigned("Dry Unknown", now - timedelta(days=31), "alias_not_registered")
    db_session.add_all([old_message, old_unassigned])
    alias.message_count = 1
    alias.last_message_at = old_message.received_at
    db_session.commit()

    result = cleanup_old_messages(
        db_session,
        message_retention_days=180,
        unassigned_retention_days=30,
        now=now,
        dry_run=True,
    )

    refreshed_alias = db_session.get(Alias, alias.id)
    assert result == {"messages_deleted": 1, "unassigned_deleted": 1, "aliases_updated": 0}
    assert db_session.query(Message).count() == 1
    assert db_session.query(UnassignedMessage).count() == 1
    assert refreshed_alias.message_count == 1
