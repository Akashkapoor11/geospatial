"""
FastAPI dependency providers.

All dependencies follow the generator pattern so that resources
(database sessions) are properly released after each request,
even if the handler raises an exception.
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.services.processor import FileProcessingService
from app.services.storage import FileStorageService


def get_container(request: Request):
    """Return the application-level dependency container stored on ``app.state``."""
    return request.app.state.container


def get_db(request: Request):
    """Yield a database session for the duration of the request.

    The session is always closed in the ``finally`` block, even when the
    route handler raises an exception.
    """
    factory: sessionmaker[Session] = request.app.state.container.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_storage_service(request: Request) -> FileStorageService:
    """Return the singleton :class:`~app.services.storage.FileStorageService`."""
    return request.app.state.container.storage_service


def get_processor(request: Request) -> FileProcessingService:
    """Return the singleton :class:`~app.services.processor.FileProcessingService`."""
    return request.app.state.container.processor
