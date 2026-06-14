from dataclasses import dataclass
from datetime import datetime
import re

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from maildrop.models import ManagedInbox, utcnow


VALID_MANAGER_STATUSES = {"pending", "used", "error"}
PREVIEW_LIMIT = 20_000
VERIFICATION_CODE_PATTERN = re.compile(r"(?<!\d)\d{4,8}(?!\d)")
VERIFICATION_KEYWORDS = (
    "验证码",
    "校验码",
    "动态码",
    "临时验证码",
    "verification code",
    "verify code",
    "security code",
    "one-time code",
    "one time code",
    "otp",
)


@dataclass(frozen=True)
class ImportRow:
    email: str
    api_url: str


@dataclass(frozen=True)
class ImportRows:
    valid: list[ImportRow]
    invalid_count: int


def normalize_manager_email(email: str) -> str:
    return email.strip().lower()


def split_import_line(line: str) -> tuple[str, str] | None:
    clean = line.strip()
    if not clean:
        return None
    if "----" in clean:
        left, right = clean.split("----", 1)
    elif "\t" in clean:
        left, right = clean.split("\t", 1)
    elif "," in clean:
        left, right = clean.split(",", 1)
    else:
        parts = clean.split(None, 1)
        if len(parts) != 2:
            return None
        left, right = parts

    email = normalize_manager_email(left)
    api_url = right.strip()
    if not email or not api_url or "@" not in email:
        return None
    if not re.match(r"^https?://", api_url):
        return None
    return email, api_url


def parse_import_rows(text: str) -> ImportRows:
    valid: list[ImportRow] = []
    invalid_count = 0
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parsed = split_import_line(line)
        if parsed is None:
            invalid_count += 1
            continue
        email, api_url = parsed
        if email in seen:
            valid = [row for row in valid if row.email != email]
        seen.add(email)
        valid.append(ImportRow(email=email, api_url=api_url))
    return ImportRows(valid=valid, invalid_count=invalid_count)


def extract_verification_codes(text: str) -> list[str]:
    lines = text.splitlines()
    codes: list[str] = []
    seen: set[str] = set()

    def add_matches(line: str) -> None:
        for match in VERIFICATION_CODE_PATTERN.findall(line):
            if match not in seen:
                seen.add(match)
                codes.append(match)

    def has_keyword(line: str) -> bool:
        lower_line = line.lower()
        return any(keyword in lower_line for keyword in VERIFICATION_KEYWORDS)

    for index, line in enumerate(lines):
        clean = line.strip()
        if not clean:
            continue
        if has_keyword(clean):
            add_matches(clean)
            for next_line in lines[index + 1 : index + 4]:
                next_clean = next_line.strip()
                if not next_clean:
                    continue
                if VERIFICATION_CODE_PATTERN.fullmatch(next_clean):
                    add_matches(next_clean)
                break
        elif VERIFICATION_CODE_PATTERN.fullmatch(clean):
            previous_lines = [item.strip() for item in lines[max(0, index - 3) : index]]
            if any(has_keyword(previous_line) for previous_line in previous_lines):
                add_matches(clean)

    if codes:
        return codes

    for line in lines:
        clean = line.strip()
        if VERIFICATION_CODE_PATTERN.fullmatch(clean):
            add_matches(clean)
    return codes


def import_managed_inboxes(db: Session, text: str) -> dict[str, int]:
    rows = parse_import_rows(text)
    created = 0
    updated = 0
    now = utcnow()
    for row in rows.valid:
        existing = db.execute(
            select(ManagedInbox).where(ManagedInbox.email == row.email)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ManagedInbox(
                    email=row.email,
                    api_url=row.api_url,
                    status="pending",
                    note="",
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1
        else:
            existing.api_url = row.api_url
            existing.updated_at = now
            updated += 1
    db.commit()
    return {"created": created, "updated": updated, "invalid": rows.invalid_count}


def manager_stats(db: Session) -> dict[str, int]:
    counts = dict(
        db.execute(select(ManagedInbox.status, func.count(ManagedInbox.id)).group_by(ManagedInbox.status)).all()
    )
    return {
        "total": int(sum(counts.values())),
        "pending": int(counts.get("pending", 0)),
        "used": int(counts.get("used", 0)),
        "error": int(counts.get("error", 0)),
    }


def manager_filter(q: str, status: str):
    clauses = []
    clean_q = q.strip()
    if clean_q:
        pattern = f"%{clean_q}%"
        clauses.append(or_(ManagedInbox.email.ilike(pattern), ManagedInbox.api_url.ilike(pattern)))
    if status in VALID_MANAGER_STATUSES:
        clauses.append(ManagedInbox.status == status)
    return clauses


def list_managed_inboxes(
    db: Session,
    *,
    q: str,
    status: str,
    page: int,
    page_size: int,
) -> tuple[list[ManagedInbox], int]:
    clauses = manager_filter(q, status)
    total_stmt = select(func.count()).select_from(ManagedInbox)
    list_stmt = select(ManagedInbox).order_by(ManagedInbox.updated_at.desc(), ManagedInbox.id.desc())
    if clauses:
        total_stmt = total_stmt.where(*clauses)
        list_stmt = list_stmt.where(*clauses)
    total = db.execute(total_stmt).scalar_one()
    items = list(
        db.execute(list_stmt.offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return items, int(total)


def bulk_update_status(db: Session, ids: list[int], status: str) -> int:
    if status not in VALID_MANAGER_STATUSES:
        raise ValueError("invalid manager status")
    clean_ids = sorted({int(item_id) for item_id in ids})
    if not clean_ids:
        return 0
    items = list(
        db.execute(select(ManagedInbox).where(ManagedInbox.id.in_(clean_ids)))
        .scalars()
        .all()
    )
    now = utcnow()
    for item in items:
        item.status = status
        item.updated_at = now
    db.commit()
    return len(items)


def delete_managed_inbox(db: Session, item_id: int) -> bool:
    result = db.execute(delete(ManagedInbox).where(ManagedInbox.id == item_id))
    db.commit()
    return bool(result.rowcount)


def update_refresh_success(
    item: ManagedInbox,
    preview: str,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or utcnow()
    item.last_preview = preview[:PREVIEW_LIMIT]
    item.last_error = None
    item.last_checked_at = current_time
    item.updated_at = current_time


def update_refresh_error(
    item: ManagedInbox,
    error: str,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or utcnow()
    item.last_error = error[:2_000]
    item.last_checked_at = current_time
    item.updated_at = current_time
    item.status = "error"
