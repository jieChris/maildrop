from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
import hashlib
import hmac
from ipaddress import ip_address, ip_network
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker as SessionMaker

from maildrop.config import Settings, get_settings
from maildrop.db import create_engine_from_url, create_schema, get_db, make_session_factory
from maildrop.mailparse import parse_message
from maildrop.models import Alias, Message, UnassignedMessage
from maildrop.repository import (
    find_alias_by_prefix,
    generate_aliases,
    ingest_parsed_message,
    latest_message_for_alias,
)
from maildrop.schemas import MessageOut
from maildrop.security import hash_token, new_token, verify_token


DEFAULT_MAX_MESSAGE_BYTES = 26_214_400
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

    def alias_view(alias: Alias, token: str | None = None) -> dict[str, object]:
        return {
            "alias": alias,
            "latest_txt_url": latest_txt_url(alias, token),
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

    def alias_filter(q: str):
        clean_q = q.strip()
        if not clean_q:
            return None
        pattern = f"%{clean_q}%"
        return or_(Alias.prefix.ilike(pattern), Alias.email.ilike(pattern))

    def paged_alias_context(
        db: Session,
        q: str,
        page: int,
        page_size: int,
        generated: list[dict[str, str]] | None = None,
    ) -> dict:
        where_clause = alias_filter(q)
        total_stmt = select(func.count()).select_from(Alias)
        list_stmt = select(Alias).order_by(Alias.created_at.desc(), Alias.id.desc())
        if where_clause is not None:
            total_stmt = total_stmt.where(where_clause)
            list_stmt = list_stmt.where(where_clause)
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
            expected_domain=app_settings.mail_domain,
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
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, q, page, page_size),
        )

    @app.post("/admin/aliases/bulk", response_class=HTMLResponse)
    def admin_bulk_aliases(
        request: Request,
        count: int = Form(..., ge=1, le=1000),
        length: int = Form(..., ge=6, le=32),
        csrf_token: str = Form(""),
        _: str = Depends(require_admin),
        db: Session = Depends(db_dep),
    ) -> HTMLResponse:
        require_csrf(request, csrf_token)
        try:
            generated_pairs = generate_aliases(
                db,
                app_settings.mail_domain,
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
            paged_alias_context(db, "", 1, 50, generated=generated),
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

        token = new_token()
        alias.api_token_hash = hash_token(token)
        db.commit()
        db.refresh(alias)

        generated = [
            {
                "email": alias.email,
                "latest_txt_url": latest_txt_url(alias, token),
            }
        ]
        return render_admin(
            request,
            "aliases.html",
            paged_alias_context(db, "", 1, 50, generated=generated),
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
