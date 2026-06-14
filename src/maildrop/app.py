from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
import hashlib
import hmac
from ipaddress import ip_address, ip_network
from pathlib import Path
import re
import secrets
import string

import httpx
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker as SessionMaker

from maildrop.config import Settings, get_settings
from maildrop.db import create_engine_from_url, create_schema, get_db, make_session_factory
from maildrop.mailparse import normalize_recipient
from maildrop.mailparse import parse_message
from maildrop.manager import (
    VALID_MANAGER_STATUSES,
    bulk_update_status,
    delete_managed_inbox,
    extract_verification_codes,
    import_managed_inboxes,
    list_managed_inboxes,
    manager_stats,
    update_refresh_error,
    update_refresh_success,
)
from maildrop.models import Alias, ManagedInbox, Message, RegisteredSubdomain, UnassignedMessage, utcnow
from maildrop.repository import (
    create_alias,
    find_alias_by_email,
    find_alias_by_prefix,
    generate_aliases,
    ingest_parsed_message,
    latest_message_for_alias,
)
from maildrop.schemas import MessageOut
from maildrop.security import hash_token, new_token, verify_token
from maildrop.spaceship import SpaceshipDnsError, SpaceshipDnsSyncClient


DEFAULT_MAX_MESSAGE_BYTES = 26_214_400
ALIAS_ALPHABET = string.ascii_lowercase + string.digits
REGISTERED_SUBDOMAIN_PARENT = "exa.aiprot.space"
REGISTERED_SUBDOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
LOCAL_INGEST_HOSTS = frozenset({"127.0.0.1", "::1", "testclient"})
LOCAL_INGEST_NETWORKS = tuple(
    ip_network(network)
    for network in (
        "127.0.0.0/8",
        "::1/128",
        "172.16.0.0/12",
    )
)


def _ingest_host_is_allowed(host: str) -> bool:
    if host in LOCAL_INGEST_HOSTS:
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in LOCAL_INGEST_NETWORKS)


async def _read_limited_body(request: Request, max_message_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_message_bytes:
            raise HTTPException(status_code=413, detail="message too large")
    return bytes(body)


def create_app(
    settings: Settings | None = None,
    session_factory: SessionMaker[Session] | None = None,
    max_message_bytes: int | None = None,
    spaceship_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    effective_max_message_bytes = max_message_bytes or app_settings.max_message_bytes
    engine: Engine | None = None
    if session_factory is None:
        engine = create_engine_from_url(app_settings.database_url)
        session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if engine is not None:
            create_schema(engine)
        yield

    app = FastAPI(title="Maildrop", docs_url=None, redoc_url=None, lifespan=lifespan)
    package_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(package_dir / "templates"))
    templates.env.globals["extract_verification_codes"] = extract_verification_codes
    basic_auth = HTTPBasic()
    app.mount(
        "/static",
        StaticFiles(directory=str(package_dir / "static")),
        name="static",
    )

    @app.middleware("http")
    async def referrer_policy_middleware(request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def db_dep() -> Generator[Session, None, None]:
        yield from get_db(session_factory)

    def require_admin(
        credentials: HTTPBasicCredentials = Depends(basic_auth),
    ) -> str:
        valid_user = secrets.compare_digest(
            credentials.username,
            app_settings.admin_username,
        )
        valid_password = secrets.compare_digest(
            credentials.password,
            app_settings.admin_password,
        )
        if not (valid_user and valid_password):
            raise HTTPException(
                status_code=401,
                detail="invalid admin credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    def csrf_secret() -> bytes:
        return f"{app_settings.admin_password}:{app_settings.ingest_token}".encode("utf-8")

    def sign_csrf_nonce(nonce: str) -> str:
        signature = hmac.new(
            csrf_secret(),
            nonce.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{nonce}.{signature}"

    def new_csrf_token() -> str:
        return sign_csrf_nonce(secrets.token_urlsafe(32))

    def csrf_token_is_valid(token: str) -> bool:
        nonce, separator, signature = token.partition(".")
        if not nonce or separator != "." or not signature:
            return False
        expected = sign_csrf_nonce(nonce)
        return hmac.compare_digest(token, expected)

    def require_csrf(request: Request, csrf_token: str) -> None:
        cookie_token = request.cookies.get("maildrop_csrf", "")
        if (
            not csrf_token
            or not cookie_token
            or not hmac.compare_digest(csrf_token, cookie_token)
            or not csrf_token_is_valid(csrf_token)
        ):
            raise HTTPException(status_code=403, detail="invalid csrf token")

    def render_admin(
        request: Request,
        template_name: str,
        context: dict,
        status_code: int = 200,
    ) -> HTMLResponse:
        token = new_csrf_token()
        response = templates.TemplateResponse(
            request,
            template_name,
            {**context, "csrf_token": token},
            status_code=status_code,
        )
        response.set_cookie(
            "maildrop_csrf",
            token,
            httponly=True,
            samesite="strict",
            secure=app_settings.app_base_url.startswith("https://"),
        )
        return response

    def latest_txt_url(alias: Alias, token: str | None = None) -> str:
        api_token = token or "token-hidden-after-creation"
        base_url = app_settings.app_base_url.rstrip("/")
        return f"{base_url}/api/inbox/{alias.prefix}/latest.txt?token={api_token}"

    def clean_domain_list(domains) -> tuple[str, ...]:
        clean_domains: list[str] = []
        seen: set[str] = set()
        for domain in domains:
            clean = domain.strip().lower()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            clean_domains.append(clean)
        return tuple(clean_domains)

    def database_registered_domains(db: Session) -> tuple[str, ...]:
        return tuple(
            db.execute(select(RegisteredSubdomain.domain).order_by(RegisteredSubdomain.domain.asc()))
            .scalars()
            .all()
        )

    def managed_mail_domains(db: Session) -> tuple[str, ...]:
        return clean_domain_list(
            [*app_settings.accepted_mail_domains, *database_registered_domains(db)]
        )

    def registered_subdomain_parent() -> str:
        return f"exa.{app_settings.mail_domain.strip().lower()}"

    def normalize_registered_subdomain(value: str) -> str:
        clean = value.strip().lower().rstrip(".")
        parent = registered_subdomain_parent()
        suffix = f".{parent}"
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]
        if "." in clean or not REGISTERED_SUBDOMAIN_LABEL_RE.fullmatch(clean):
            raise ValueError("invalid subdomain")
        return f"{clean}.{parent}"

    def alias_count_for_domain(db: Session, domain: str) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(Alias)
                .where(func.lower(Alias.email).like(f"%@{domain}"))
            ).scalar_one()
        )

    def mail_domain_options(db: Session) -> list[dict[str, object]]:
        return [
            {
                "domain": domain,
                "alias_count": alias_count_for_domain(db, domain),
            }
            for domain in managed_mail_domains(db)
        ]

    def subdomain_context(db: Session, notice: str = "") -> dict[str, object]:
        env_domains = set(app_settings.registered_mail_subdomains)
        db_domains = list(
            db.execute(select(RegisteredSubdomain).order_by(RegisteredSubdomain.domain.asc()))
            .scalars()
            .all()
        )
        rows: list[dict[str, object]] = []
        for domain in app_settings.registered_mail_subdomains:
            rows.append(
                {
                    "id": None,
                    "domain": domain,
                    "source": "配置文件",
                    "alias_count": alias_count_for_domain(db, domain),
                    "deletable": False,
                }
            )
        for item in db_domains:
            if item.domain in env_domains:
                continue
            alias_count = alias_count_for_domain(db, item.domain)
            rows.append(
                {
                    "id": item.id,
                    "domain": item.domain,
                    "source": "后台登记",
                    "alias_count": alias_count,
                    "deletable": alias_count == 0,
                }
            )
        return {
            "title": "子域名管理",
            "subdomains": rows,
            "parent_domain": registered_subdomain_parent(),
            "spaceship_enabled": spaceship_api_is_configured(),
            "notice": notice,
        }

    def spaceship_api_is_configured() -> bool:
        return bool(
            app_settings.spaceship_api_key
            and app_settings.spaceship_api_secret
            and app_settings.spaceship_dns_domain
            and app_settings.spaceship_auto_register_txt_prefix
        )

    def spaceship_sync_client() -> SpaceshipDnsSyncClient:
        if not spaceship_api_is_configured():
            raise HTTPException(status_code=400, detail="spaceship api is not configured")
        return SpaceshipDnsSyncClient(
            api_key=app_settings.spaceship_api_key,
            api_secret=app_settings.spaceship_api_secret,
            domain=app_settings.spaceship_dns_domain,
            base_url=app_settings.spaceship_api_base_url,
            transport=spaceship_transport,
        )

    def sync_spaceship_openai_subdomains(db: Session) -> str:
        try:
            records = spaceship_sync_client().openai_verification_subdomains(
                parent_domain=registered_subdomain_parent(),
                txt_prefix=app_settings.spaceship_auto_register_txt_prefix,
            )
        except SpaceshipDnsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        existing = set(managed_mail_domains(db))
        created: list[str] = []
        skipped = 0
        for record in records:
            try:
                domain = normalize_registered_subdomain(record.domain)
            except ValueError:
                skipped += 1
                continue
            if domain in existing:
                skipped += 1
                continue
            db.add(RegisteredSubdomain(domain=domain))
            existing.add(domain)
            created.append(domain)
        db.commit()
        if created:
            return f"从 Spaceship TXT 记录新增 {len(created)} 个：{', '.join(created)}；跳过 {skipped} 个"
        return f"没有新增子域名；跳过 {skipped} 个"

    def alias_route_key_for_recipient(db: Session, local_part: str, domain: str) -> str:
        clean_local = local_part.strip().lower()
        clean_domain = domain.strip().lower()
        if clean_domain == app_settings.mail_domain.strip().lower():
            base_key = clean_local
        else:
            domain_key = clean_domain.replace(".", "-")
            base_key = f"{clean_local}--{domain_key}"

        route_key = base_key
        counter = 2
        while True:
            existing = find_alias_by_prefix(db, route_key)
            if existing is None or existing.email == f"{clean_local}@{clean_domain}":
                return route_key
            route_key = f"{base_key}-{counter}"
            counter += 1

    def generate_aliases_for_domain(
        db: Session,
        domain: str,
        *,
        count: int,
        length: int,
    ) -> list[tuple[Alias, str]]:
        clean_domain = domain.strip().lower()
        if clean_domain not in managed_mail_domains(db):
            raise ValueError("unsupported mail domain")
        if clean_domain == app_settings.mail_domain.strip().lower():
            return generate_aliases(db, clean_domain, count=count, length=length)
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        if length < 6 or length > 32:
            raise ValueError("length must be between 6 and 32")

        created: list[tuple[Alias, str]] = []
        while len(created) < count:
            local_part = "".join(secrets.choice(ALIAS_ALPHABET) for _ in range(length))
            email = f"{local_part}@{clean_domain}"
            if find_alias_by_email(db, email) is not None:
                continue
            route_key = alias_route_key_for_recipient(db, local_part, clean_domain)
            alias, token = create_alias(
                db,
                route_key,
                clean_domain,
                email=email,
                commit=False,
            )
            created.append((alias, token))

        db.commit()
        for alias, _token in created:
            db.refresh(alias)
        return created

    def alias_view(alias: Alias, token: str | None = None) -> dict[str, object]:
        if alias.deleted_at is not None:
            category = "已删除"
        elif alias.exported_at is not None:
            category = "已导出"
        else:
            category = "未导出"
        return {
            "alias": alias,
            "category": category,
            "latest_txt_url": latest_txt_url(alias, token),
        }

    def rotate_alias_token_view(alias: Alias) -> dict[str, str]:
        token = new_token()
        alias.api_token_hash = hash_token(token)
        return {
            "email": alias.email,
            "latest_txt_url": latest_txt_url(alias, token),
        }

    def exported_alias_links(aliases: list[dict[str, str]]) -> PlainTextResponse:
        lines = [f"{item['email']} {item['latest_txt_url']}" for item in aliases]
        body = "\n".join(lines) + "\n"
        return PlainTextResponse(
            body,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=maildrop-alias-links.txt"
            },
        )

    def soft_delete_alias(alias: Alias) -> None:
        if alias.deleted_at is None:
            alias.deleted_at = utcnow()
        alias.enabled = False

    def register_unassigned_as_managed_inbox(
        db: Session,
        message_id: int,
    ) -> dict[str, object]:
        seed = db.get(UnassignedMessage, message_id)
        if seed is None:
            raise HTTPException(status_code=404, detail="unassigned message not found")

        recipient = normalize_recipient(seed.recipient)
        if "@" not in recipient:
            raise HTTPException(status_code=400, detail="invalid recipient")
        prefix, domain = recipient.rsplit("@", 1)
        if domain not in managed_mail_domains(db):
            raise HTTPException(status_code=400, detail="recipient domain is not managed")

        alias = find_alias_by_email(db, recipient)
        if alias is None:
            route_key = alias_route_key_for_recipient(db, prefix, domain)
            alias, token = create_alias(db, route_key, domain, email=recipient, commit=False)
            api_url = latest_txt_url(alias, token)
        else:
            alias.enabled = True
            alias.deleted_at = None
            api_url = rotate_alias_token_view(alias)["latest_txt_url"]

        messages = list(
            db.execute(
                select(UnassignedMessage)
                .where(UnassignedMessage.recipient == recipient)
                .order_by(UnassignedMessage.received_at.asc(), UnassignedMessage.id.asc())
            )
            .scalars()
            .all()
        )
        for message in messages:
            db.add(
                Message(
                    alias_id=alias.id,
                    recipient=message.recipient,
                    sender=message.sender,
                    subject=message.subject,
                    received_at=message.received_at,
                    text_body=message.text_body,
                    html_body=message.html_body,
                    raw_mime=message.raw_mime,
                    headers_json=message.headers_json,
                )
            )
            db.delete(message)

        if messages:
            alias.message_count = int(alias.message_count or 0) + len(messages)
            latest_received_at = max(message.received_at for message in messages)
            if alias.last_message_at is None or latest_received_at > alias.last_message_at:
                alias.last_message_at = latest_received_at

        now = utcnow()
        managed = db.execute(
            select(ManagedInbox).where(ManagedInbox.email == recipient)
        ).scalar_one_or_none()
        if managed is None:
            db.add(
                ManagedInbox(
                    email=recipient,
                    api_url=api_url,
                    status="pending",
                    note="",
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            managed.api_url = api_url
            managed.updated_at = now

        db.commit()
        return {
            "email": recipient,
            "api_url": api_url,
            "migrated": len(messages),
        }

    def pagination(page: int, page_size: int, total: int) -> dict[str, int | bool]:
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

    def manager_status_label(status: str) -> str:
        return {"pending": "待消耗", "used": "已消耗", "error": "错误"}.get(status, status)

    def managed_item_payload(item: ManagedInbox) -> dict[str, object]:
        return {
            "id": item.id,
            "email": item.email,
            "api_url": item.api_url,
            "status": item.status,
            "status_label": manager_status_label(item.status),
            "last_preview": item.last_preview,
            "last_error": item.last_error,
            "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
            "codes": extract_verification_codes(item.last_preview or ""),
        }

    def refresh_managed_item(item: ManagedInbox) -> None:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(item.api_url)
            if response.status_code != 200:
                update_refresh_error(item, f"HTTP {response.status_code}")
            else:
                update_refresh_success(item, response.text)
        except Exception as exc:
            update_refresh_error(item, str(exc))

    def manager_context(
        db: Session,
        *,
        q: str,
        status: str,
        page: int,
        page_size: int,
        import_summary: dict[str, int] | None = None,
        notice: str = "",
    ) -> dict:
        items, total = list_managed_inboxes(
            db,
            q=q,
            status=status,
            page=page,
            page_size=page_size,
        )
        return {
            "title": "收件管理器",
            "items": items,
            "q": q,
            "status": status,
            "status_options": [
                ("all", "全部"),
                ("pending", "待消耗"),
                ("used", "已消耗"),
                ("error", "错误"),
            ],
            "status_label": manager_status_label,
            "stats": manager_stats(db),
            "pagination": pagination(page, page_size, total),
            "import_summary": import_summary,
            "notice": notice,
        }

    def alias_filter(q: str):
        clean_q = q.strip()
        if not clean_q:
            return None
        pattern = f"%{clean_q}%"
        return or_(Alias.prefix.ilike(pattern), Alias.email.ilike(pattern))

    def alias_category_filter(category: str):
        if category == "unexported":
            return Alias.deleted_at.is_(None), Alias.exported_at.is_(None)
        if category == "exported":
            return Alias.deleted_at.is_(None), Alias.exported_at.is_not(None)
        if category == "deleted":
            return (Alias.deleted_at.is_not(None),)
        return ()

    def alias_domain_filter(mail_domain: str):
        clean_domain = mail_domain.strip().lower()
        if not clean_domain:
            return None
        return clean_domain, func.lower(Alias.email).like(f"%@{clean_domain}")

    def require_managed_mail_domain(db: Session, domain: str) -> None:
        clean_domain = domain.strip().lower()
        if clean_domain and clean_domain not in managed_mail_domains(db):
            raise HTTPException(status_code=400, detail="unsupported mail domain")

    def paged_alias_context(
        db: Session,
        q: str,
        category: str,
        page: int,
        page_size: int,
        mail_domain_filter: str = "",
        generated: list[dict[str, str]] | None = None,
    ) -> dict:
        where_clause = alias_filter(q)
        total_stmt = select(func.count()).select_from(Alias)
        list_stmt = select(Alias).order_by(Alias.created_at.desc(), Alias.id.desc())
        if where_clause is not None:
            total_stmt = total_stmt.where(where_clause)
            list_stmt = list_stmt.where(where_clause)
        category_clauses = alias_category_filter(category)
        if category_clauses:
            total_stmt = total_stmt.where(*category_clauses)
            list_stmt = list_stmt.where(*category_clauses)
        domain_filter = alias_domain_filter(mail_domain_filter)
        if domain_filter is not None:
            clean_domain, domain_clause = domain_filter
            require_managed_mail_domain(db, clean_domain)
            total_stmt = total_stmt.where(domain_clause)
            list_stmt = list_stmt.where(domain_clause)
        total = db.execute(total_stmt).scalar_one()
        aliases = (
            db.execute(list_stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )
        return {
            "title": "邮箱别名",
            "aliases": [alias_view(alias) for alias in aliases],
            "generated": generated or [],
            "q": q,
            "category": category,
            "mail_domains": managed_mail_domains(db),
            "mail_domain_options": mail_domain_options(db),
            "mail_domain_filter": mail_domain_filter.strip().lower(),
            "pagination": pagination(page, page_size, total),
        }

    def authorized_alias(prefix: str, token: str, db: Session) -> Alias:
        alias = find_alias_by_prefix(db, prefix)
        if alias is None:
            raise HTTPException(status_code=404, detail="alias not found")
        if not alias.enabled:
            raise HTTPException(status_code=403, detail="alias disabled")
        if not verify_token(token, alias.api_token_hash):
            raise HTTPException(status_code=403, detail="invalid token")
        return alias

    @app.get("/api/health")
    def health(db: Session = Depends(db_dep)) -> dict[str, bool]:
        db.execute(text("select 1"))
        return {"success": True}

    @app.post("/internal/ingest", status_code=202)
    async def ingest(
        request: Request,
        x_envelope_recipient: str = Header(alias="X-Envelope-Recipient"),
        x_ingest_token: str = Header(default="", alias="X-Ingest-Token"),
        db: Session = Depends(db_dep),
    ) -> dict[str, str]:
        if request.client is None or not _ingest_host_is_allowed(request.client.host):
            raise HTTPException(status_code=403, detail="ingest must be local")
        if x_ingest_token != app_settings.ingest_token:
            raise HTTPException(status_code=401, detail="invalid ingest token")

        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > effective_max_message_bytes:
            raise HTTPException(status_code=413, detail="message too large")

        raw = await _read_limited_body(request, effective_max_message_bytes)
        parsed = parse_message(raw, x_envelope_recipient)
        status = ingest_parsed_message(
            db,
            parsed,
            expected_domain=managed_mail_domains(db),
        )
        return {"status": status}

    @app.get("/api/inbox/{prefix}/latest.txt", response_class=PlainTextResponse)
    def latest_txt(
        prefix: str,
        token: str = Query(...),
        db: Session = Depends(db_dep),
    ) -> str:
        alias = authorized_alias(prefix, token, db)
        message = latest_message_for_alias(db, alias)
        if message is None:
            raise HTTPException(status_code=404, detail="no messages")
        return (
            f"From: {message.sender}\n"
            f"To: {message.recipient}\n"
            f"Subject: {message.subject}\n"
            f"Received: {message.received_at.isoformat()}\n\n"
            f"{message.text_body}"
        )

    @app.get("/api/inbox/{prefix}/latest.json", response_model=MessageOut)
    def latest_json(
        prefix: str,
        token: str = Query(...),
        db: Session = Depends(db_dep),
    ) -> Message:
        alias = authorized_alias(prefix, token, db)
        message = latest_message_for_alias(db, alias)
        if message is None:
            raise HTTPException(status_code=404, detail="no messages")
        return message

    @app.get("/api/inbox/{prefix}/messages.json", response_model=list[MessageOut])
    def messages_json(
        prefix: str,
        token: str = Query(...),
        limit: int = Query(20, ge=1, le=100),
        db: Session = Depends(db_dep),
    ) -> list[Message]:
        alias = authorized_alias(prefix, token, db)
        return list(
            db.execute(
                select(Message)
                .where(Message.alias_id == alias.id)
                .order_by(Message.received_at.desc(), Message.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    @app.get("/admin", response_class=HTMLResponse)
    def admin_aliases(
        request: Request,
        q: str = Query("", max_length=128),
        category: str = Query("all", pattern="^(all|unexported|exported|deleted)$"),
        mail_domain: str = Query("", max_length=320),
        mail_domain_filter: str = Query("", max_length=320),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        selected_mail_domain = mail_domain_filter or mail_domain
        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, q, category, page, page_size, selected_mail_domain),
        )

    @app.get("/admin/subdomains", response_class=HTMLResponse)
    def admin_subdomains(
        request: Request,
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        return render_admin(request, "subdomains.html", subdomain_context(db))

    @app.post("/admin/subdomains")
    def admin_add_subdomain(
        request: Request,
        subdomain: str = Form(..., max_length=128),
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> RedirectResponse:
        require_csrf(request, csrf_token)
        try:
            domain = normalize_registered_subdomain(subdomain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if domain not in managed_mail_domains(db):
            db.add(RegisteredSubdomain(domain=domain))
            db.commit()
        return RedirectResponse("/admin/subdomains", status_code=303)

    @app.post("/admin/subdomains/sync-spaceship", response_class=HTMLResponse)
    def admin_sync_spaceship_subdomains(
        request: Request,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        notice = sync_spaceship_openai_subdomains(db)
        return render_admin(request, "subdomains.html", subdomain_context(db, notice=notice))

    @app.post("/admin/subdomains/{subdomain_id}/delete")
    def admin_delete_subdomain(
        request: Request,
        subdomain_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> RedirectResponse:
        require_csrf(request, csrf_token)
        item = db.get(RegisteredSubdomain, subdomain_id)
        if item is None:
            raise HTTPException(status_code=404, detail="subdomain not found")
        if alias_count_for_domain(db, item.domain):
            raise HTTPException(status_code=400, detail="subdomain has aliases")
        db.delete(item)
        db.commit()
        return RedirectResponse("/admin/subdomains", status_code=303)

    @app.get("/xxxmailmanage", response_class=HTMLResponse)
    def xxxmailmanage(
        request: Request,
        q: str = Query("", max_length=256),
        status: str = Query("all", pattern="^(all|pending|used|error)$"),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(db, q=q, status=status, page=page, page_size=page_size),
        )

    @app.post("/xxxmailmanage/import", response_class=HTMLResponse)
    def xxxmailmanage_import(
        request: Request,
        rows: str = Form(""),
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        summary = import_managed_inboxes(db, rows)
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(
                db,
                q="",
                status="all",
                page=1,
                page_size=50,
                import_summary=summary,
            ),
        )

    @app.post("/xxxmailmanage/status", response_class=HTMLResponse)
    def xxxmailmanage_bulk_status(
        request: Request,
        csrf_token: str = Form(""),
        ids: list[int] | None = Form(None),
        status: str = Form(...),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        try:
            updated = bulk_update_status(db, ids or [], status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(
                db,
                q="",
                status="all",
                page=1,
                page_size=50,
                notice=f"已更新 {updated} 条记录",
            ),
        )

    @app.post("/xxxmailmanage/{item_id}/status", response_class=HTMLResponse)
    def xxxmailmanage_item_status(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        status: str = Form(...),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        if status not in VALID_MANAGER_STATUSES:
            raise HTTPException(status_code=400, detail="invalid manager status")
        item = db.get(ManagedInbox, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="managed inbox not found")
        item.status = status
        item.updated_at = utcnow()
        db.commit()
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(db, q="", status="all", page=1, page_size=50),
        )

    @app.post("/xxxmailmanage/{item_id}/status.json")
    def xxxmailmanage_item_status_json(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        status: str = Form(...),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> dict[str, object]:
        require_csrf(request, csrf_token)
        if status not in VALID_MANAGER_STATUSES:
            raise HTTPException(status_code=400, detail="invalid manager status")
        item = db.get(ManagedInbox, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="managed inbox not found")
        item.status = status
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
        return {"item": managed_item_payload(item), "stats": manager_stats(db)}

    @app.post("/xxxmailmanage/{item_id}/refresh", response_class=HTMLResponse)
    def xxxmailmanage_refresh(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        item = db.get(ManagedInbox, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="managed inbox not found")
        refresh_managed_item(item)
        db.commit()
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(db, q="", status="all", page=1, page_size=50),
        )

    @app.post("/xxxmailmanage/{item_id}/refresh.json")
    def xxxmailmanage_refresh_json(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> dict[str, object]:
        require_csrf(request, csrf_token)
        item = db.get(ManagedInbox, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="managed inbox not found")
        refresh_managed_item(item)
        db.commit()
        db.refresh(item)
        return {"item": managed_item_payload(item), "stats": manager_stats(db)}

    @app.post("/xxxmailmanage/{item_id}/delete", response_class=HTMLResponse)
    def xxxmailmanage_delete(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        delete_managed_inbox(db, item_id)
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(db, q="", status="all", page=1, page_size=50),
        )

    @app.post("/xxxmailmanage/{item_id}/delete.json")
    def xxxmailmanage_delete_json(
        request: Request,
        item_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> dict[str, object]:
        require_csrf(request, csrf_token)
        deleted = delete_managed_inbox(db, item_id)
        return {
            "deleted": deleted,
            "item_id": item_id,
            "stats": manager_stats(db),
        }

    @app.post("/admin/aliases/bulk", response_class=HTMLResponse)
    def admin_bulk_aliases(
        request: Request,
        count: int = Form(..., ge=1, le=1000),
        length: int = Form(..., ge=6, le=32),
        mail_domain: str = Form(""),
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        try:
            generated_pairs = generate_aliases_for_domain(
                db,
                mail_domain or app_settings.mail_domain,
                count=count,
                length=length,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        generated = [
            {
                "email": alias.email,
                "latest_txt_url": latest_txt_url(alias, token),
            }
            for alias, token in generated_pairs
        ]
        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, "", "all", 1, 50, mail_domain or "", generated=generated),
        )

    @app.post("/admin/aliases/{prefix}/token", response_class=HTMLResponse)
    def admin_rotate_alias_token(
        request: Request,
        prefix: str,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        alias = find_alias_by_prefix(db, prefix)
        if alias is None:
            raise HTTPException(status_code=404, detail="alias not found")

        generated = [rotate_alias_token_view(alias)]
        db.commit()
        db.refresh(alias)

        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, "", "all", 1, 50, generated=generated),
        )

    @app.post("/admin/aliases/export", response_class=PlainTextResponse)
    def admin_export_aliases(
        request: Request,
        csrf_token: str = Form(""),
        scope: str = Form(""),
        prefixes: list[str] | None = Form(None),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> PlainTextResponse:
        require_csrf(request, csrf_token)
        if scope == "all":
            aliases = list(
                db.execute(
                    select(Alias)
                    .where(Alias.deleted_at.is_(None), Alias.enabled.is_(True))
                    .order_by(Alias.email.asc(), Alias.id.asc())
                )
                .scalars()
                .all()
            )
        else:
            clean_prefixes = sorted({prefix.strip().lower() for prefix in prefixes or [] if prefix.strip()})
            if not clean_prefixes:
                raise HTTPException(status_code=400, detail="select aliases or export all")
            aliases = list(
                db.execute(
                    select(Alias)
                    .where(
                        Alias.prefix.in_(clean_prefixes),
                        Alias.deleted_at.is_(None),
                        Alias.enabled.is_(True),
                    )
                    .order_by(Alias.email.asc(), Alias.id.asc())
                )
                .scalars()
                .all()
            )

        if not aliases:
            raise HTTPException(status_code=400, detail="no aliases to export")

        exported_at = utcnow()
        for alias in aliases:
            alias.exported_at = exported_at
        exported = [rotate_alias_token_view(alias) for alias in aliases]
        db.commit()
        return exported_alias_links(exported)

    @app.post("/admin/aliases/delete", response_class=HTMLResponse)
    def admin_delete_selected_aliases(
        request: Request,
        csrf_token: str = Form(""),
        prefixes: list[str] | None = Form(None),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        clean_prefixes = sorted({prefix.strip().lower() for prefix in prefixes or [] if prefix.strip()})
        if not clean_prefixes:
            raise HTTPException(status_code=400, detail="select aliases to delete")

        aliases = list(
            db.execute(select(Alias).where(Alias.prefix.in_(clean_prefixes)))
            .scalars()
            .all()
        )
        for alias in aliases:
            soft_delete_alias(alias)
        db.commit()

        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, "", "deleted", 1, 50),
        )

    @app.post("/admin/aliases/{prefix}/delete", response_class=HTMLResponse)
    def admin_delete_alias(
        request: Request,
        prefix: str,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        alias = find_alias_by_prefix(db, prefix)
        if alias is None:
            raise HTTPException(status_code=404, detail="alias not found")

        soft_delete_alias(alias)
        db.commit()

        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, "", "deleted", 1, 50),
        )

    @app.get("/admin/unassigned", response_class=HTMLResponse)
    def admin_unassigned(
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        total = db.execute(select(func.count()).select_from(UnassignedMessage)).scalar_one()
        messages = (
            db.execute(
                select(UnassignedMessage)
                .order_by(
                    UnassignedMessage.received_at.desc(),
                    UnassignedMessage.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return render_admin(
            request,
            "unassigned.html",
            {
                "title": "未登记邮件",
                "messages": messages,
                "pagination": pagination(page, page_size, total),
            },
        )

    @app.post("/admin/unassigned/{message_id}/register-import", response_class=HTMLResponse)
    def admin_register_unassigned_import(
        request: Request,
        message_id: int,
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        result = register_unassigned_as_managed_inbox(db, message_id)
        email = str(result["email"])
        migrated = int(result["migrated"])
        return render_admin(
            request,
            "xxxmailmanage.html",
            manager_context(
                db,
                q=email,
                status="all",
                page=1,
                page_size=50,
                notice=f"已登记并导入 {email}，迁移 {migrated} 封邮件",
            ),
        )

    @app.get("/admin/aliases/{prefix}/messages", response_class=HTMLResponse)
    def admin_alias_messages(
        request: Request,
        prefix: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        alias = find_alias_by_prefix(db, prefix)
        if alias is None:
            raise HTTPException(status_code=404, detail="alias not found")

        total = db.execute(
            select(func.count()).select_from(Message).where(Message.alias_id == alias.id)
        ).scalar_one()
        messages = (
            db.execute(
                select(Message)
                .where(Message.alias_id == alias.id)
                .order_by(Message.received_at.desc(), Message.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return render_admin(
            request,
            "messages.html",
            {
                "title": f"{alias.email} 最近邮件",
                "alias": alias,
                "messages": messages,
                "pagination": pagination(page, page_size, total),
            },
        )

    return app
