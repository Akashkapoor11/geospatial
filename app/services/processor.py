"""
File processing service — orchestrates reading, feature extraction, and measurement.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import mapping

from app.core.errors import GeospatialProcessingError
from app.db.models import Feature, Measurement, UploadedFile
from app.geospatial.measurement import MeasurementEngine, MeasurementResult
from app.geospatial.reader import GeospatialFileReader
from app.geospatial.utils import json_safe

logger = logging.getLogger(__name__)


class FileProcessingService:
    """
    Orchestrates the full file-processing pipeline:
      1. Read geospatial file (KML or Shapefile ZIP) into a GeoDataFrame.
      2. Extract each feature into the database.
      3. Calculate measurements (area / length) in a projected CRS.
      4. Persist results and update the file status.

    Per-feature errors are isolated — a single bad feature does not abort the rest.
    """

    def __init__(
        self,
        session_factory,
        reader: GeospatialFileReader,
        measurement_engine: MeasurementEngine,
    ):
        self.session_factory = session_factory
        self.reader = reader
        self.measurement_engine = measurement_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, file_id: str) -> None:
        """Entry point called as a FastAPI BackgroundTask."""
        session = self.session_factory()
        try:
            record = session.get(UploadedFile, file_id)
            if record is None:
                logger.error("Processing requested for unknown file id=%s", file_id)
                return

            record.status = "PROCESSING"
            record.processing_started_at = datetime.now(timezone.utc)
            record.error_message = None
            session.commit()

            read_result = self.reader.read(Path(record.stored_path), record.file_type, file_id)
            gdf = read_result.geo_dataframe

            source_crs = self._crs_label(gdf)
            record.source_crs = source_crs
            record.feature_count = int(len(gdf))

            if len(gdf) == 0:
                raise GeospatialProcessingError("The uploaded dataset contains no features.")

            for feature_index, (_, row) in enumerate(gdf.iterrows()):
                feature = self._build_feature(
                    file_id=file_id,
                    feature_index=feature_index,
                    row=row,
                    source_crs=source_crs,
                )
                session.add(feature)
                session.flush()  # Populate feature.id before creating Measurement

                measurement = self._safe_measurement(row.geometry, gdf.crs)
                session.add(
                    Measurement(
                        feature_id=feature.id,
                        measurement_type=measurement.measurement_type,
                        value=measurement.value,
                        unit=measurement.unit,
                        measurement_crs=measurement.measurement_crs,
                        status=measurement.status,
                        message=measurement.message,
                        geometry_repaired=measurement.geometry_repaired,
                    )
                )

            record.status = "COMPLETED"
            record.processing_completed_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(
                "Processing completed file_id=%s features=%d crs=%s",
                file_id,
                record.feature_count,
                source_crs,
            )

        except Exception as exc:
            session.rollback()
            try:
                record = session.get(UploadedFile, file_id)
                if record is not None:
                    record.status = "FAILED"
                    record.error_message = str(exc)
                    record.processing_completed_at = datetime.now(timezone.utc)
                    session.commit()
            except Exception:
                logger.exception("Failed to persist FAILED status for file_id=%s", file_id)

            logger.exception("File processing failed file_id=%s", file_id)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_feature(
        self,
        file_id: str,
        feature_index: int,
        row,
        source_crs: str | None,
    ) -> Feature:
        try:
            geometry = row.geometry
            geometry_payload = mapping(geometry) if geometry is not None else None
            geometry_type = geometry.geom_type if geometry is not None else "Unknown"
            properties = {
                str(key): json_safe(value)
                for key, value in row.drop(labels=["geometry"]).to_dict().items()
            }
            is_valid = bool(geometry is not None and geometry.is_valid)
            validity_issue = None

            if geometry is not None and not geometry.is_valid:
                try:
                    from shapely.validation import explain_validity

                    validity_issue = explain_validity(geometry)
                except Exception:
                    validity_issue = "Invalid geometry (details unavailable)"

            return Feature(
                file_id=file_id,
                feature_index=feature_index,
                geometry_type=geometry_type,
                geometry=json_safe(geometry_payload),
                properties=properties,
                source_crs=source_crs,
                is_valid=is_valid,
                validity_issue=validity_issue,
            )
        except Exception as exc:
            logger.warning(
                "Feature extraction failed file_id=%s index=%d: %s",
                file_id,
                feature_index,
                exc,
            )
            return Feature(
                file_id=file_id,
                feature_index=feature_index,
                geometry_type="Unknown",
                geometry=None,
                properties={},
                source_crs=source_crs,
                is_valid=False,
                validity_issue=f"Feature extraction failed: {exc}",
            )

    def _safe_measurement(self, geometry, source_crs) -> MeasurementResult:
        try:
            crs = CRS.from_user_input(source_crs) if source_crs is not None else None
            return self.measurement_engine.measure(geometry, crs)
        except Exception as exc:
            logger.exception("Measurement failure for a single feature")
            return MeasurementResult(
                measurement_type=None,
                value=None,
                unit=None,
                measurement_crs=None,
                status="FAILED",
                message=f"Measurement failed: {exc}",
            )

    @staticmethod
    def _crs_label(gdf: gpd.GeoDataFrame) -> str | None:
        if gdf.crs is None:
            return None
        crs = CRS.from_user_input(gdf.crs)
        epsg = crs.to_epsg()
        return f"EPSG:{epsg}" if epsg is not None else crs.to_string()
