from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.session import sessionmaker as SessionMaker

from maildrop.models import Base


def create_engine_from_url(database_url: str, **kwargs: Any) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True, **kwargs)


def make_session_factory(engine: Engine) -> SessionMaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def get_db(session_factory: SessionMaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session
