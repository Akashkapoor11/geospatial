"""
Pydantic request/response schemas for the Geospatial File Measurement API.

All ORM-backed schemas use ``ConfigDict(from_attributes=True)`` so they
can be constructed directly from SQLAlchemy model instances.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Upload / File info
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Immediate response returned after a file is accepted for processing.

    The file is persisted and background processing has been queued.
    Poll ``GET /api/files/{id}/`` until ``status`` is ``COMPLETED``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique file identifier (UUID)")
    filename: str = Field(..., description="Original filename as uploaded")
    file_type: str = Field(..., description="Detected type: 'kml' or 'shapefile_zip'")
    file_size: int = Field(..., description="File size in bytes")
    status: str = Field(..., description="Processing status: UPLOADED | PROCESSING | COMPLETED | FAILED")
    created_at: datetime = Field(..., description="UTC timestamp of upload")


class FileInfoResponse(UploadResponse):
    """Detailed file record returned by ``GET /api/files/{id}/``.

    Extends :class:`UploadResponse` with processing results populated
    after the background job completes.
    """

    feature_count: int | None = Field(None, description="Number of features extracted")
    crs: str | None = Field(None, description="Source CRS label (e.g. 'EPSG:4326')")
    error_message: str | None = Field(None, description="Error detail when status is FAILED")
    processing_started_at: datetime | None = Field(None, description="UTC timestamp when processing began")
    processing_completed_at: datetime | None = Field(None, description="UTC timestamp when processing finished")
    updated_at: datetime | None = Field(None, description="UTC timestamp of last record update")


class FileListResponse(BaseModel):
    """Paginated list of uploaded files."""

    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of files matching the query")
    items: list[FileInfoResponse]


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


class MeasurementItem(BaseModel):
    """Measurement result for a single feature.

    ``measurement`` is ``null`` when measurement is not applicable or failed.
    Check ``status`` for the reason.
    """

    feature_id: int = Field(..., description="Database ID of the feature")
    feature_index: int = Field(..., description="Zero-based index of the feature in the file")
    geometry_type: str = Field(..., description="Shapely geometry type string")
    source_crs: str | None = Field(None, description="CRS of the source dataset")
    measurement_type: str | None = Field(None, description="'area' or 'length', or null")
    measurement: float | None = Field(None, description="Calculated value, or null")
    unit: str | None = Field(None, description="Unit of measurement: 'm²', 'm', 'ft', etc.")
    measurement_crs: str | None = Field(None, description="Projected CRS used for measurement")
    status: str = Field(
        ...,
        description=(
            "COMPLETED — measurement successful | "
            "NOT_REQUIRED — Point/MultiPoint | "
            "UNSUPPORTED — geometry type not eligible | "
            "UNAVAILABLE — source CRS unknown | "
            "FAILED — unexpected error"
        ),
    )
    message: str | None = Field(None, description="Human-readable explanation of the status")
    geometry_repaired: bool = Field(
        False,
        description="True if the geometry was automatically repaired with make_valid() before measurement",
    )


class MeasurementPage(BaseModel):
    """Paginated collection of measurements for a file."""

    file_id: str = Field(..., description="UUID of the parent file")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of features/measurements")
    items: list[MeasurementItem]


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class FeatureItem(BaseModel):
    """Full feature record including raw geometry (GeoJSON) and properties."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID of the feature")
    feature_index: int = Field(..., description="Zero-based index of the feature in the file")
    geometry_type: str = Field(..., description="Shapely geometry type (e.g. 'Polygon')")
    geometry: dict[str, Any] | None = Field(None, description="GeoJSON geometry object")
    properties: dict[str, Any] = Field(..., description="Feature attributes from the source file")
    source_crs: str | None = Field(None, description="CRS label of the source dataset")
    is_valid: bool = Field(..., description="Whether the geometry passed Shapely validity check")
    validity_issue: str | None = Field(
        None,
        description="Shapely validity issue description (null when is_valid=true)",
    )


class FeaturePage(BaseModel):
    """Paginated collection of features for a file."""

    file_id: str = Field(..., description="UUID of the parent file")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of features")
    items: list[FeatureItem]


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(..., description="Human-readable error description")


class ReadinessResponse(BaseModel):
    """Response body for the ``/ready`` readiness probe."""

    status: str = Field(..., description="'ready' when all dependencies are healthy")
    database: str = Field(..., description="'ok' when the database is reachable")


# ---------------------------------------------------------------------------
# Shared query params (not currently used as a dependency but available)
# ---------------------------------------------------------------------------


class PageParams(BaseModel):
    """Reusable pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number, 1-indexed")
    page_size: int = Field(default=50, ge=1, le=500, description="Items per page")
