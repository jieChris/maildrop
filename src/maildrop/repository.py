from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
import secrets
import string

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from maildrop.mailparse import ParsedMessage, normalize_recipient
from maildrop.models import Alias, Message, UnassignedMessage
from maildrop.security import hash_token, new_token


ALPHABET = string.ascii_lowercase + string.digits
PREFIX_CHARS = frozenset(ALPHABET + "-_.")


def prefix_from_email(email: str) -> str:
    return normalize_recipient(email).split("@", 1)[0]


def create_alias(
    db: Session,
    prefix: str,
    domain: str,
    note: str = "",
    email: str | None = None,
    commit: bool = True,
) -> tuple[Alias, str]:
    clean_prefix = prefix.strip().lower()
    clean_domain = domain.strip().lower()
    if not clean_prefix:
        raise ValueError("prefix must not be empty")
    if not clean_domain:
        raise ValueError("domain must not be empty")
    if any(ch not in PREFIX_CHARS for ch in clean_prefix):
        raise ValueError("prefix contains unsupported characters")

    token = new_token()
    alias = Alias(
        prefix=clean_prefix,
        email=(email.strip().lower() if email is not None else f"{clean_prefix}@{clean_domain}"),
        api_token_hash=hash_token(token),
        enabled=True,
        note=note,
    )
    db.add(alias)
    db.flush()
    if commit:
        db.commit()
        db.refresh(alias)
    return alias, token


def generate_aliases(
    db: Session,
    domain: str,
    count: int,
    length: int = 12,
) -> list[tuple[Alias, str]]:
    if count < 1 or count > 1000:
        raise ValueError("count must be between 1 and 1000")
    if length < 6 or length > 32:
        raise ValueError("length must be between 6 and 32")

    created: list[tuple[Alias, str]] = []
    existing = set(db.execute(select(Alias.prefix)).scalars())

    while len(created) < count:
        prefix = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if prefix in existing:
            continue
        alias, token = create_alias(db, prefix, domain, commit=False)
        existing.add(prefix)
        created.append((alias, token))

    db.commit()
    for alias, _token in created:
        db.refresh(alias)
    return created


def find_alias_by_prefix(db: Session, prefix: str) -> Alias | None:
    return db.execute(
        select(Alias).where(Alias.prefix == prefix.strip().lower())
    ).scalar_one_or_none()


def find_alias_by_email(db: Session, email: str) -> Alias | None:
    return db.execute(
        select(Alias).where(Alias.email == normalize_recipient(email))
    ).scalar_one_or_none()


def accepted_domain_set(expected_domain: str | Iterable[str]) -> set[str]:
    if isinstance(expected_domain, str):
        domains = [expected_domain]
    else:
        domains = list(expected_domain)
    return {domain.strip().lower() for domain in domains if domain.strip()}


def _store_unassigned(db: Session, parsed: ParsedMessage, recipient: str, reason: str) -> None:
    db.add(
        UnassignedMessage(
            recipient=recipient,
            sender=parsed.sender,
            subject=parsed.subject,
            text_body=parsed.text_body,
            html_body=parsed.html_body,
            raw_mime=parsed.raw_mime,
            headers_json=parsed.headers,
            reason=reason,
        )
    )


def ingest_parsed_message(
    db: Session,
    parsed: ParsedMessage,
    expected_domain: str | Iterable[str],
) -> str:
    recipient = normalize_recipient(parsed.recipient)
    prefix, domain = recipient.rsplit("@", 1)

    if domain not in accepted_domain_set(expected_domain):
        _store_unassigned(db, parsed, recipient, "domain_not_allowed")
        db.commit()
        return "unassigned"

    alias = find_alias_by_email(db, recipient)
    if alias is None:
        _store_unassigned(db, parsed, recipient, "alias_not_registered")
        db.commit()
        return "unassigned"

    if alias.deleted_at is not None:
        _store_unassigned(db, parsed, recipient, "alias_deleted")
        db.commit()
        return "unassigned"

    if not alias.enabled:
        _store_unassigned(db, parsed, recipient, "alias_disabled")
        db.commit()
        return "unassigned"

    now = datetime.now(timezone.utc)
    db.add(
        Message(
            alias_id=alias.id,
            recipient=recipient,
            sender=parsed.sender,
            subject=parsed.subject,
            received_at=now,
            text_body=parsed.text_body,
            html_body=parsed.html_body,
            raw_mime=parsed.raw_mime,
            headers_json=parsed.headers,
        )
    )
    alias.last_message_at = now
    alias.message_count += 1
    db.commit()
    return "assigned"


def latest_message_for_alias(db: Session, alias: Alias) -> Message | None:
    return (
        db.execute(
            select(Message)
            .where(Message.alias_id == alias.id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def cleanup_old_messages(
    db: Session,
    *,
    message_retention_days: int,
    unassigned_retention_days: int,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    if message_retention_days <= 0 or unassigned_retention_days <= 0:
        raise ValueError("retention days must be positive")

    current_time = now or datetime.now(timezone.utc)
    message_cutoff = current_time - timedelta(days=message_retention_days)
    unassigned_cutoff = current_time - timedelta(days=unassigned_retention_days)

    affected_alias_ids = set(
        db.execute(
            select(Message.alias_id).where(Message.received_at < message_cutoff).distinct()
        ).scalars()
    )

    messages_deleted = db.execute(
        select(func.count(Message.id)).where(Message.received_at < message_cutoff)
    ).scalar_one()
    unassigned_deleted = db.execute(
        select(func.count(UnassignedMessage.id)).where(
            UnassignedMessage.received_at < unassigned_cutoff
        )
    ).scalar_one()

    if dry_run:
        return {
            "messages_deleted": int(messages_deleted),
            "unassigned_deleted": int(unassigned_deleted),
            "aliases_updated": 0,
        }

    db.execute(delete(Message).where(Message.received_at < message_cutoff))
    db.execute(delete(UnassignedMessage).where(UnassignedMessage.received_at < unassigned_cutoff))

    aliases_updated = 0
    for alias_id in affected_alias_ids:
        alias = db.get(Alias, alias_id)
        if alias is None:
            continue
        count, last_message_at = db.execute(
            select(func.count(Message.id), func.max(Message.received_at)).where(
                Message.alias_id == alias_id
            )
        ).one()
        alias.message_count = int(count or 0)
        alias.last_message_at = last_message_at
        aliases_updated += 1

    db.commit()
    return {
        "messages_deleted": int(messages_deleted),
        "unassigned_deleted": int(unassigned_deleted),
        "aliases_updated": aliases_updated,
    }
