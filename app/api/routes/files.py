"""
File API routes — upload, retrieve, list, delete, features, measurements.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_processor, get_storage_service
from app.api.schemas import (
    FeatureItem,
    FeaturePage,
    FileInfoResponse,
    FileListResponse,
    MeasurementItem,
    MeasurementPage,
    UploadResponse,
)
from app.core.errors import InvalidArchiveError, UnsupportedFileError
from app.db.models import Feature, Measurement, UploadedFile
from app.db.repositories import FileRepository
from app.services.processor import FileProcessingService
from app.services.storage import FileStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_file_or_404(db: Session, file_id: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


def _storage_file_type(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower()
    return "kml" if suffix == "kml" else "shapefile_zip"


# ---------------------------------------------------------------------------
# POST /api/files/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a geospatial file",
    description=(
        "Upload a `.kml` file or a `.zip` archive containing a Shapefile. "
        "The file is stored and geospatial processing begins asynchronously. "
        "Poll `GET /api/files/{id}/` for the processing status."
    ),
)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="KML file or ZIP archive containing a Shapefile"),
    storage: FileStorageService = Depends(get_storage_service),
    processor: FileProcessingService = Depends(get_processor),
    db: Session = Depends(get_db),
) -> UploadResponse:
    try:
        file_id, filename, file_size, stored_path = await storage.save_upload(file)
    except (UnsupportedFileError, InvalidArchiveError) as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    record = UploadedFile(
        id=file_id,
        filename=filename,
        file_type=_storage_file_type(filename),
        file_size=file_size,
        stored_path=str(stored_path),
        status="UPLOADED",
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(processor.process, file_id)

    return UploadResponse.model_validate(record, from_attributes=True)


# ---------------------------------------------------------------------------
# GET /api/files/
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=FileListResponse,
    summary="List uploaded files",
    description="Returns a paginated list of all uploaded files and their processing status.",
)
def list_files(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=200, description="Items per page"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
) -> FileListResponse:
    query = select(UploadedFile)
    count_query = select(func.count()).select_from(UploadedFile)

    if status_filter:
        query = query.where(UploadedFile.status == status_filter.upper())
        count_query = count_query.where(UploadedFile.status == status_filter.upper())

    total = db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    records = list(db.scalars(query.order_by(UploadedFile.created_at.desc()).offset(offset).limit(page_size)))

    return FileListResponse(
        page=page,
        page_size=page_size,
        total=total,
        items=[
            FileInfoResponse.model_validate(r, from_attributes=True).model_copy(update={"crs": r.source_crs})
            for r in records
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/",
    response_model=FileInfoResponse,
    summary="Get file information",
    description="Returns metadata and processing status for a previously uploaded file.",
)
def get_file(
    file_id: str,
    db: Session = Depends(get_db),
) -> FileInfoResponse:
    record = _get_file_or_404(db, file_id)
    return FileInfoResponse.model_validate(record, from_attributes=True).model_copy(
        update={"crs": record.source_crs}
    )


# ---------------------------------------------------------------------------
# DELETE /api/files/{file_id}/
# ---------------------------------------------------------------------------


@router.delete(
    "/{file_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded file",
    description=(
        "Permanently deletes the file record, all associated features, "
        "measurements, and the stored file on disk."
    ),
)
def delete_file(
    file_id: str,
    storage: FileStorageService = Depends(get_storage_service),
    db: Session = Depends(get_db),
) -> None:
    record = _get_file_or_404(db, file_id)
    stored_path = record.stored_path
    try:
        db.delete(record)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Best-effort disk cleanup — do not fail the request if the file is already gone
    storage.delete_stored_file(stored_path)


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/measurements/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementPage,
    summary="Get feature measurements",
    description=(
        "Returns area/length measurements for every feature in the file. "
        "Requires the file to have completed processing. "
        "Point geometries carry status `NOT_REQUIRED`; unsupported types carry `UNSUPPORTED`."
    ),
)
def get_measurements(
    file_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> MeasurementPage:
    record = _get_file_or_404(db, file_id)

    if record.status not in {"COMPLETED", "FAILED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Measurements are not ready. Current status: {record.status}.",
        )

    if record.status == "FAILED" and not db.scalar(
        select(func.count())
        .select_from(Measurement)
        .join(Feature, Feature.id == Measurement.feature_id)
        .where(Feature.file_id == file_id)
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Processing failed: {record.error_message}",
        )

    repo = FileRepository(db)
    offset = (page - 1) * page_size
    measurement_rows = repo.list_measurements(file_id, offset, page_size)
    total = repo.count_measurements(file_id)

    feature_map = {
        feature.id: feature
        for feature in db.scalars(
            select(Feature).where(Feature.id.in_([m.feature_id for m in measurement_rows]))
        )
    }

    items = [
        MeasurementItem(
            feature_id=measurement.feature_id,
            feature_index=feature_map[measurement.feature_id].feature_index,
            geometry_type=feature_map[measurement.feature_id].geometry_type,
            source_crs=feature_map[measurement.feature_id].source_crs,
            measurement_type=measurement.measurement_type,
            measurement=measurement.value,
            unit=measurement.unit,
            measurement_crs=measurement.measurement_crs,
            status=measurement.status,
            message=measurement.message,
            geometry_repaired=measurement.geometry_repaired,
        )
        for measurement in measurement_rows
    ]

    return MeasurementPage(
        file_id=file_id,
        page=page,
        page_size=page_size,
        total=total,
        items=items,
    )


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/features/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/features/",
    response_model=FeaturePage,
    summary="Get extracted features",
    description=(
        "Returns the raw extracted features (geometry + properties) "
        "from the uploaded file. Available as soon as processing is COMPLETED."
    ),
)
def get_features(
    file_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> FeaturePage:
    _get_file_or_404(db, file_id)  # raises 404 if file does not exist

    repo = FileRepository(db)
    offset = (page - 1) * page_size
    items = repo.list_features(file_id, offset, page_size)
    total = repo.count_features(file_id)

    return FeaturePage(
        file_id=file_id,
        page=page,
        page_size=page_size,
        total=total,
        items=[FeatureItem.model_validate(item, from_attributes=True) for item in items],
    )


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/features/{feature_id}/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/features/{feature_id}/",
    response_model=FeatureItem,
    summary="Get a single feature",
    description="Returns full geometry, properties, and validity information for one feature.",
)
def get_feature(
    file_id: str,
    feature_id: int,
    db: Session = Depends(get_db),
) -> FeatureItem:
    _get_file_or_404(db, file_id)

    feature = db.scalar(
        select(Feature).where(Feature.id == feature_id, Feature.file_id == file_id)
    )
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found.")

    return FeatureItem.model_validate(feature, from_attributes=True)
