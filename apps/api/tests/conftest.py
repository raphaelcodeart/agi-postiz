"""
Shared fixtures.

Most tests in this suite are pure unit tests over pure functions and need
nothing from here. The participation tests do: the rules they cover - who is
still in a line-up, who may put a channel back, what a launch resolves to - are
statements about rows, and testing them against a fake session would only pin
the fake.

The database is therefore real, but disposable: a schema created from the
models, dropped afterwards, inside its own database so nothing can reach the
application's data. When no server is available the fixture skips rather than
fails, so the suite still runs anywhere.
"""
import os
import uuid
from contextlib import closing

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker


def _admin_url() -> str:
    """
    Connection string for the server, pointed at the maintenance database.

    Reads DATABASE_URL because that is what the application already needs to be
    configured with; only the database name is swapped, never the host or
    credentials.
    """
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        return ""
    url = sa.engine.make_url(raw)
    if not url.drivername.startswith("postgresql"):
        return ""
    # render_as_string(hide_password=False), NOT str(): str() on a URL replaces
    # the password with "***", which produces a connection string that looks
    # right in a log and fails authentication every time.
    return url.set(database="postgres").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def db_engine():
    admin_url = _admin_url()
    if not admin_url:
        pytest.skip("No PostgreSQL DATABASE_URL configured; database tests skipped.")

    name = f"agipost_test_{uuid.uuid4().hex[:12]}"
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # noqa: BLE001 - unreachable server is a skip, not a failure
        admin_engine.dispose()
        pytest.skip(f"PostgreSQL not reachable ({exc.__class__.__name__}); database tests skipped.")

    test_url = sa.engine.make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    engine = sa.create_engine(test_url)

    # Import through db.base so every model is registered on the metadata -
    # create_all only builds the tables it knows about, and a missing import
    # shows up as a foreign key to a table that does not exist.
    from app.db.base import Base  # noqa: F401

    Base.metadata.create_all(engine)

    try:
        yield engine
    finally:
        engine.dispose()
        with closing(admin_engine.connect()) as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin_engine.dispose()


@pytest.fixture()
def db(db_engine) -> Session:
    """
    A session whose writes are discarded.

    Everything runs inside one outer transaction that is rolled back at the end,
    so tests see a clean schema without paying to recreate it each time - and a
    test that commits (the participation service does, deliberately) still cannot
    leak into the next one.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    """
    FastAPI test client wired to the throwaway database.

    The portal endpoints are worth testing through HTTP rather than by calling
    the functions: their whole job is to scope what one signed-in user can see,
    and that scoping lives in the dependency that resolves the token as much as
    in the query underneath it.
    """
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def portal_token():
    """Mints a portal session for a user, the way logging in would."""
    from app.core.security import TOKEN_TYPE_PORTAL_USER, SecurityService

    def _token(user):
        token = SecurityService.create_access_token(
            subject=user.id, token_type=TOKEN_TYPE_PORTAL_USER
        )
        return {"Authorization": f"Bearer {token}"}

    return _token
