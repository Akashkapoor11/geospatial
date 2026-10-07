"""
Test configuration and shared fixtures for the Geospatial File Measurement API.

Fixtures
--------
app
    FastAPI application instance configured with an isolated SQLite database
    and temporary storage root. Each test gets a fresh, clean state.

client
    FastAPI ``TestClient`` wrapping the ``app`` fixture.
    ``TestClient`` runs ``BackgroundTasks`` synchronously, so tests can
    assert on COMPLETED status without any polling or sleeping.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def app(tmp_path: Path):
    """Return a FastAPI app wired to an isolated SQLite DB and temp storage.

    The ``max_upload_size_mb=5`` limit is intentionally low to make the
    upload-size-limit test feasible without sending a real 50 MB file.
    """
    db_path = tmp_path / "test.sqlite3"
    settings = Settings(
        app_name="Test Geospatial API",
        database_url=f"sqlite:///{db_path}",
        storage_root=tmp_path / "storage",
        auto_create_db=True,
        max_upload_size_mb=5,
        max_zip_entries=50,
        max_zip_uncompressed_mb=10,
    )
    return create_app(settings)


@pytest.fixture()
def client(app):
    """Return an HTTPX ``TestClient`` for the test app.

    FastAPI ``TestClient`` runs ``BackgroundTasks`` synchronously, so any
    test that uploads a file can immediately query the measurements endpoint
    without polling.
    """
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
