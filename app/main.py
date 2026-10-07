"""
Application factory for the Geospatial File Measurement API.

Creates the FastAPI application with:
  - Dependency injection container
  - Database engine and session factory
  - CORS middleware
  - API routers (health, files)
  - Lifespan handler for startup/shutdown
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import files, health
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.database import create_db_engine, create_session_factory, create_tables
from app.geospatial.measurement import MeasurementEngine
from app.geospatial.reader import GeospatialFileReader
from app.services.processor import FileProcessingService
from app.services.storage import FileStorageService


# ---------------------------------------------------------------------------
# Dependency injection container
# ---------------------------------------------------------------------------


@dataclass
class AppContainer:
    """Holds application-level singleton dependencies."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    storage_service: FileStorageService
    processor: FileProcessingService


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build and return the FastAPI application.

    Accepts an optional ``settings`` override, which is used in tests to
    provide an in-memory SQLite database and an isolated storage root.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    container = AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        storage_service=FileStorageService(settings),
        processor=FileProcessingService(
            session_factory=session_factory,
            reader=GeospatialFileReader(settings),
            measurement_engine=MeasurementEngine(),
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Auto-create tables for SQLite / local dev when AUTO_CREATE_DB=true.
        # Production uses Alembic (AUTO_CREATE_DB=false).
        if settings.auto_create_db:
            create_tables(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        description=(
            "Upload a **KML** file or a **Shapefile ZIP** archive and receive "
            "CRS-aware area and length measurements for every feature.\n\n"
            "### Supported geometry measurements\n"
            "| Geometry | Measurement |\n"
            "|---|---|\n"
            "| Polygon / MultiPolygon | Area (m²) |\n"
            "| LineString / MultiLineString | Length (m) |\n"
            "| Point / MultiPoint | Not required |\n"
            "| Other | Gracefully unsupported |\n\n"
            "### Processing flow\n"
            "Files are accepted synchronously and processed asynchronously. "
            "Poll `GET /api/files/{id}/` to check status.\n\n"
            "### CRS handling\n"
            "Geographic coordinates (e.g. EPSG:4326) are automatically reprojected "
            "to an appropriate local UTM or azimuthal projection before measurement."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "files",
                "description": "Upload geospatial files and retrieve features and measurements.",
            },
            {
                "name": "health",
                "description": "Liveness and readiness probes.",
            },
            {
                "name": "meta",
                "description": "API metadata.",
            },
        ],
        license_info={
            "name": "MIT",
        },
        contact={
            "name": "Geospatial API",
        },
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(files.router)

    @app.get("/", tags=["meta"], summary="API information")
    def root():
        """Returns basic API metadata and links to documentation."""
        return {
            "name": "Geospatial File Measurement API",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "health": "/health",
            "ready": "/ready",
        }

    return app


app = create_app()
