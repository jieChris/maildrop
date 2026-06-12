from sqlalchemy import inspect, text

from maildrop.db import create_schema, get_db, make_session_factory
from maildrop.models import Alias, IngestEvent, Message, UnassignedMessage


def test_alias_message_relationship(db_session):
    alias = Alias(
        prefix="alpha",
        email="alpha@aiprot.space",
        api_token_hash="hash",
        enabled=True,
    )
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
    assert stored is not None
    assert stored.email == "alpha@aiprot.space"
    assert stored.note == ""
    assert stored.enabled is True
    assert stored.message_count == 0
    assert stored.messages[0].subject == "Hello"
    assert stored.messages[0].alias is stored


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

    stored = db_session.query(UnassignedMessage).one()
    assert stored.recipient == "unknown@aiprot.space"
    assert stored.html_body == ""
    assert stored.reason == "alias_not_registered"


def test_ingest_event_records_status(db_session):
    event = IngestEvent(
        recipient="alpha@aiprot.space",
        status="stored",
        detail="message stored",
    )
    db_session.add(event)
    db_session.commit()

    stored = db_session.query(IngestEvent).one()
    assert stored.recipient == "alpha@aiprot.space"
    assert stored.status == "stored"
    assert stored.detail == "message stored"
    assert stored.created_at is not None


def test_create_schema_creates_expected_tables(engine):
    create_schema(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "aliases",
        "messages",
        "unassigned_messages",
        "ingest_events",
    }.issubset(tables)


def test_get_db_yields_session_from_explicit_factory(engine):
    session_factory = make_session_factory(engine)

    generator = get_db(session_factory)
    session = next(generator)
    try:
        assert session.execute(text("select 1")).scalar_one() == 1
    finally:
        try:
            next(generator)
        except StopIteration:
            pass
