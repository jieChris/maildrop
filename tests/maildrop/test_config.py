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
        max_message_bytes=10_485_760,
        message_retention_days=90,
        unassigned_retention_days=14,
    )

    assert settings.app_base_url == "https://aiprot.space"
    assert settings.mail_domain == "aiprot.space"
    assert settings.accepted_mail_domains == ("aiprot.space",)
    assert settings.admin_username == "admin"
    assert settings.ingest_token == "ingest-secret"
    assert settings.max_message_bytes == 10_485_760
    assert settings.message_retention_days == 90
    assert settings.unassigned_retention_days == 14


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


def test_settings_parses_additional_mail_domains():
    settings = Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        mail_domains="aiprot.space, SSN.aiprot.space, sso.aiprot.space",
        database_url="sqlite+pysqlite:///:memory:",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
    )

    assert settings.accepted_mail_domains == (
        "aiprot.space",
        "ssn.aiprot.space",
        "sso.aiprot.space",
    )


def test_settings_parses_registered_exa_subdomains_as_accepted_domains():
    settings = Settings(
        app_base_url="https://aiprot.space",
        mail_domain="aiprot.space",
        mail_domains="aiprot.space,ssn.aiprot.space",
        mail_registered_subdomains="a.exa.aiprot.space, B.exa.aiprot.space",
        database_url="sqlite+pysqlite:///:memory:",
        admin_username="admin",
        admin_password="admin-secret",
        ingest_token="ingest-secret",
    )

    assert settings.registered_mail_subdomains == (
        "a.exa.aiprot.space",
        "b.exa.aiprot.space",
    )
    assert settings.accepted_mail_domains == (
        "aiprot.space",
        "ssn.aiprot.space",
        "a.exa.aiprot.space",
        "b.exa.aiprot.space",
    )


def test_settings_rejects_non_positive_message_limit():
    with pytest.raises(ValueError):
        Settings(
            app_base_url="https://aiprot.space",
            mail_domain="aiprot.space",
            database_url="sqlite+pysqlite:///:memory:",
            admin_username="admin",
            admin_password="admin-secret",
            ingest_token="ingest-secret",
            max_message_bytes=0,
        )


def test_settings_rejects_non_positive_retention_days():
    with pytest.raises(ValueError):
        Settings(
            app_base_url="https://aiprot.space",
            mail_domain="aiprot.space",
            database_url="sqlite+pysqlite:///:memory:",
            admin_username="admin",
            admin_password="admin-secret",
            ingest_token="ingest-secret",
            message_retention_days=0,
        )

    with pytest.raises(ValueError):
        Settings(
            app_base_url="https://aiprot.space",
            mail_domain="aiprot.space",
            database_url="sqlite+pysqlite:///:memory:",
            admin_username="admin",
            admin_password="admin-secret",
            ingest_token="ingest-secret",
            unassigned_retention_days=-1,
        )
