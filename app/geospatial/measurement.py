"""
Measurement engine — CRS-aware area and length calculations.

Supported geometry types and their measurements:

  Polygon / MultiPolygon    → area  (m² in projected CRS)
  LineString / MultiLine    → length (m in projected CRS)
  Point / MultiPoint        → NOT_REQUIRED  (no measurement needed)
  GeometryCollection        → UNSUPPORTED   (graceful, no crash)
  Anything else             → UNSUPPORTED   (graceful, no crash)

Invalid geometries are detected via Shapely and automatically repaired
with ``make_valid()`` before measurement when possible.  The
``geometry_repaired`` flag is set to True in that case.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import (
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity, make_valid

from app.core.errors import GeospatialProcessingError
from app.geospatial.crs import choose_measurement_crs

logger = logging.getLogger(__name__)

MeasurementStatus = Literal[
    "COMPLETED",
    "NOT_REQUIRED",
    "UNSUPPORTED",
    "UNAVAILABLE",
    "FAILED",
]

# Geometry types eligible for area measurement
_AREA_TYPES = (Polygon, MultiPolygon)

# Geometry types eligible for length measurement
_LINE_TYPE_NAMES = frozenset({"LineString", "MultiLineString"})

# Geometry types that explicitly need no measurement
_POINT_TYPES = (Point, MultiPoint)


@dataclass(frozen=True)
class MeasurementResult:
    """Immutable result object returned by :class:`MeasurementEngine`."""

    measurement_type: str | None
    value: float | None
    unit: str | None
    measurement_crs: str | None
    status: MeasurementStatus
    message: str | None
    geometry_repaired: bool = False


class MeasurementEngine:
    """CRS-aware geometry measurement engine.

    Usage::

        engine = MeasurementEngine()
        result = engine.measure(shapely_geometry, pyproj_crs)
    """

    def measure(self, geometry: BaseGeometry | None, source_crs: CRS | None) -> MeasurementResult:
        """Measure *geometry* using a projected CRS derived from *source_crs*.

        Parameters
        ----------
        geometry:
            A Shapely geometry object, or ``None`` for a feature with no geometry.
        source_crs:
            The coordinate reference system of the source dataset, or ``None``
            when the CRS is unknown.

        Returns
        -------
        MeasurementResult
            Always returns a result — never raises for unsupported/null geometry.
        """
        if geometry is None or geometry.is_empty:
            return MeasurementResult(
                measurement_type=None,
                value=None,
                unit=None,
                measurement_crs=None,
                status="FAILED",
                message="The feature has no usable geometry.",
            )

        geom_type = geometry.geom_type

        if isinstance(geometry, _POINT_TYPES):
            return MeasurementResult(
                measurement_type=None,
                value=None,
                unit=None,
                measurement_crs=None,
                status="NOT_REQUIRED",
                message="Point geometries do not require a measurement.",
            )

        if isinstance(geometry, _AREA_TYPES):
            return self._measure_polygon(geometry, source_crs)

        if geom_type in _LINE_TYPE_NAMES:
            return self._measure_line(geometry, source_crs)

        # GeometryCollection and any other exotic types
        return MeasurementResult(
            measurement_type=None,
            value=None,
            unit=None,
            measurement_crs=None,
            status="UNSUPPORTED",
            message=f"Measurement is not supported for geometry type '{geom_type}'.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_geometry(geometry: BaseGeometry) -> tuple[BaseGeometry, bool, str | None]:
        """Validate and optionally repair *geometry*.

        Returns
        -------
        (prepared_geometry, was_repaired, validity_issue_description)
        """
        if geometry.is_valid:
            return geometry, False, None

        issue = explain_validity(geometry)
        logger.debug("Attempting geometry repair: %s", issue)

        try:
            repaired = make_valid(geometry)
        except Exception as exc:
            logger.warning("make_valid() failed: %s", exc)
            return geometry, False, issue

        if repaired.is_empty:
            logger.warning("Repaired geometry is empty; using original: %s", issue)
            return geometry, False, issue

        return repaired, True, issue

    def _measure_polygon(self, geometry: BaseGeometry, source_crs: CRS | None) -> MeasurementResult:
        prepared, repaired, issue = self._prepare_geometry(geometry)

        if source_crs is None:
            return MeasurementResult(
                measurement_type="area",
                value=None,
                unit=None,
                measurement_crs=None,
                status="UNAVAILABLE",
                message="Cannot calculate area reliably because the source CRS is unknown.",
                geometry_repaired=repaired,
            )

        decision = choose_measurement_crs(prepared, source_crs, "polygon")

        try:
            projected = (
                gpd.GeoSeries([prepared], crs=source_crs)
                .to_crs(CRS.from_user_input(decision.measurement_crs))
                .iloc[0]
            )
            value = float(projected.area)
        except Exception as exc:
            raise GeospatialProcessingError(f"Area calculation failed: {exc}") from exc

        unit = "m²" if decision.linear_unit == "m" else f"{decision.linear_unit}²"
        message = decision.reason
        if repaired:
            message = (
                f"Geometry was repaired before measurement. "
                f"Original validity issue: {issue}. {message}"
            )

        return MeasurementResult(
            measurement_type="area",
            value=round(value, 6),
            unit=unit,
            measurement_crs=decision.measurement_crs,
            status="COMPLETED",
            message=message,
            geometry_repaired=repaired,
        )

    def _measure_line(self, geometry: BaseGeometry, source_crs: CRS | None) -> MeasurementResult:
        prepared, repaired, issue = self._prepare_geometry(geometry)

        if source_crs is None:
            return MeasurementResult(
                measurement_type="length",
                value=None,
                unit=None,
                measurement_crs=None,
                status="UNAVAILABLE",
                message="Cannot calculate length reliably because the source CRS is unknown.",
                geometry_repaired=repaired,
            )

        decision = choose_measurement_crs(prepared, source_crs, "linear")

        try:
            projected = (
                gpd.GeoSeries([prepared], crs=source_crs)
                .to_crs(CRS.from_user_input(decision.measurement_crs))
                .iloc[0]
            )
            value = float(projected.length)
        except Exception as exc:
            raise GeospatialProcessingError(f"Length calculation failed: {exc}") from exc

        message = decision.reason
        if repaired:
            message = (
                f"Geometry was repaired before measurement. "
                f"Original validity issue: {issue}. {message}"
            )

        return MeasurementResult(
            measurement_type="length",
            value=round(value, 6),
            unit=decision.linear_unit,
            measurement_crs=decision.measurement_crs,
            status="COMPLETED",
            message=message,
            geometry_repaired=repaired,
        )
