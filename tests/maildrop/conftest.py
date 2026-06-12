import pytest
from sqlalchemy.pool import StaticPool

from maildrop.db import create_engine_from_url, create_schema, make_session_factory


@pytest.fixture()
def engine():
    engine = create_engine_from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(engine)
    return engine


@pytest.fixture()
def db_session(engine):
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        yield session
