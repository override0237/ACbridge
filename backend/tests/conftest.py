"""Test fixtures.

By default tests run on an in-memory SQLite database (zero setup). To run the SAME tests against
real PostgreSQL (recommended before demos - it exercises row locks and native UUID/JSONB):

    TEST_DATABASE_URL=postgresql+psycopg://acbridge:acbridge@localhost:5432/acbridge_test pytest
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"          # set BEFORE importing the app
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["PROBATION_HOURS"] = "0"      # most tests are not about the cooling-off period; dedicated tests enable it
os.environ["EVIDENCE_UPLOAD_DIR"] = "/tmp/acbridge_test_uploads"
os.environ["SUPPORTED_TOWNS"] = "buea,limbe"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db, make_engine
from app.main import app
from app.models import Base
from app.security.rate_limit import reset_rate_limits
from tests.helpers import World

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")
IS_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")


@pytest.fixture
def session_factory():
    if TEST_DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import create_engine, event
        engine = create_engine(
            TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    else:
        engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    reset_rate_limits()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def world(client, session_factory) -> World:
    return World(client, session_factory)
