"""
SQLAlchemy database engine, session factory, and table management.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base


def create_db_engine(settings: Settings) -> Engine:
    """Create and return a SQLAlchemy :class:`~sqlalchemy.engine.Engine`.

    Automatically enables WAL mode for SQLite (improves concurrent read
    performance during background processing) and sets ``pool_pre_ping``
    for PostgreSQL to detect stale connections before use.

    Parameters
    ----------
    settings:
        Application settings containing the database URL.
    """
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args: dict = {}

    if is_sqlite:
        # Allow SQLite to be used from multiple threads (needed because
        # BackgroundTasks runs in a threadpool separate from the main thread).
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        # For SQLite, use a StaticPool or NullPool in tests; defaults work for production.
        # For PostgreSQL, tune pool_size/max_overflow via env if needed.
    )

    if is_sqlite:
        # Enable WAL journal mode on every new SQLite connection for better
        # concurrency between the API thread and background processing threads.
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a :class:`~sqlalchemy.orm.sessionmaker` bound to *engine*."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def create_tables(engine: Engine) -> None:
    """Create all ORM-mapped tables if they do not exist.

    Used for local development and tests (``AUTO_CREATE_DB=true``).
    Production deployments use Alembic migrations instead.
    """
    Base.metadata.create_all(bind=engine)


def get_session(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield a session and guarantee it is closed after the caller returns.

    Intended for use as a FastAPI dependency via :func:`app.api.dependencies.get_db`.
    """
    session = factory()
    try:
        yield session
    finally:
        session.close()
