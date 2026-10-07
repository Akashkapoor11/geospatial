"""
Health and readiness endpoints.

/health  — liveness probe: returns 200 as long as the process is alive.
/ready   — readiness probe: returns 200 only when the database is reachable.
"""
from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.schemas import ReadinessResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    description=(
        "Simple liveness check. Returns `200 OK` as long as the application "
        "process is running. Used by container orchestrators to decide whether "
        "to restart the container."
    ),
)
def health():
    """Return a static alive signal."""
    return {"status": "ok"}


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Readiness check that verifies database connectivity. "
        "Returns `200 OK` when the database is reachable, "
        "`503 Service Unavailable` otherwise. "
        "Used by load balancers to route traffic only to healthy instances."
    ),
)
def ready(db: Session = Depends(get_db)) -> ReadinessResponse:
    """Verify that the database can execute a trivial query."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database is unavailable: {exc}",
        ) from exc

    return ReadinessResponse(status="ready", database="ok")
