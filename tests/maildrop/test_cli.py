from datetime import datetime, timedelta, timezone
import json

from maildrop import cli
from maildrop.db import make_session_factory
from maildrop.models import Message
from maildrop.repository import create_alias


def test_cleanup_cli_uses_settings_and_supports_dry_run(engine, monkeypatch, capsys):
    session_factory = make_session_factory(engine)
    with session_factory() as db:
        alias, _ = create_alias(db, "cli", "aiprot.space")
        db.add(
            Message(
                alias_id=alias.id,
                recipient=alias.email,
                sender="sender@example.com",
                subject="Expired",
                received_at=datetime.now(timezone.utc) - timedelta(days=181),
                text_body="Expired",
                html_body="",
                raw_mime="Expired raw",
                headers_json={},
            )
        )
        alias.message_count = 1
        db.commit()

    class TestSettings:
        database_url = "sqlite+pysqlite:///:memory:"
        message_retention_days = 180
        unassigned_retention_days = 30

    monkeypatch.setattr(cli, "get_settings", lambda: TestSettings())
    monkeypatch.setattr(cli, "create_engine_from_url", lambda _database_url: engine)

    assert cli.main(["cleanup", "--dry-run"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output == {"aliases_updated": 0, "messages_deleted": 1, "unassigned_deleted": 0}
    with session_factory() as db:
        assert db.query(Message).count() == 1
