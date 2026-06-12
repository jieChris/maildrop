from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_adds_alias_lifecycle_columns_to_existing_schema(tmp_path):
    database_path = tmp_path / "maildrop.db"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table aliases (
                    id integer primary key,
                    prefix varchar(128) not null,
                    email varchar(320) not null,
                    api_token_hash varchar(128) not null,
                    enabled boolean not null default 1,
                    note text not null default '',
                    created_at datetime not null,
                    last_message_at datetime,
                    message_count integer not null default 0
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into aliases (
                    id, prefix, email, api_token_hash, enabled, note, created_at, message_count
                ) values (
                    1, 'alpha', 'alpha@aiprot.space', 'hash', 1, '', '2026-06-12 00:00:00', 0
                )
                """
            )
        )

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("aliases")}
    assert "exported_at" in columns
    assert "deleted_at" in columns
    with engine.connect() as connection:
        row = connection.execute(
            text("select prefix, exported_at, deleted_at from aliases where id = 1")
        ).one()
    assert row.prefix == "alpha"
    assert row.exported_at is None
    assert row.deleted_at is None
