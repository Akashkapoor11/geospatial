"""
CRS selection strategy for geospatial measurements.

The goal is to always calculate area and length in a metric projected
coordinate system — never in raw degrees.

Decision order
--------------
1. Source CRS unknown          → return UNAVAILABLE decision (no measurement)
2. Source CRS already projected → use it as-is, report its linear unit
3. Source CRS is geographic    → estimate best-fit UTM zone via GeoPandas
4. UTM estimation failed       → build local azimuthal projection from centroid
5. Source CRS is neither       → build local azimuthal projection from centroid
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CRSDecision:
    """Encapsulates the chosen measurement CRS and the reason for the choice."""

    source_crs: str | None
    """Human-readable label of the source CRS (e.g. ``"EPSG:4326"``), or ``None``."""

    measurement_crs: str | None
    """Human-readable label of the CRS used for measurement, or ``None`` when unavailable."""

    linear_unit: str | None
    """Linear unit string (``"m"``, ``"ft"``, ``"yd"``), or ``None`` when unavailable."""

    reason: str
    """Short human-readable explanation of why this CRS was chosen."""


def crs_label(crs: CRS | None) -> str | None:
    """Return a canonical EPSG label or PROJ string for *crs*, or ``None``."""
    if crs is None:
        return None
    epsg = crs.to_epsg()
    if epsg is not None:
        return f"EPSG:{epsg}"
    return crs.to_string()


def _linear_unit(crs: CRS) -> str:
    """Return the linear unit name for a projected *crs* (``"m"``, ``"ft"``, etc.)."""
    if not crs.axis_info:
        return "unit"
    name = (crs.axis_info[0].unit_name or "").lower()
    if "metre" in name or "meter" in name:
        return "m"
    if "foot" in name or "feet" in name:
        return "ft"
    if "yard" in name:
        return "yd"
    return crs.axis_info[0].unit_name or "unit"


def _local_fallback_crs(geometry: BaseGeometry, family: str) -> CRS:
    """Build a local azimuthal projection centred on *geometry*'s representative point.

    Parameters
    ----------
    geometry:
        Source geometry used to derive the centre point.
    family:
        ``"linear"`` → Azimuthal Equidistant (best length accuracy).
        anything else → Local Equal-Area Azimuthal (best area accuracy).
    """
    point = geometry.representative_point()
    longitude = float(point.x)
    latitude = float(point.y)

    projection = "aeqd" if family == "linear" else "laea"
    logger.debug(
        "Building local %s projection at lon=%.4f lat=%.4f",
        projection,
        longitude,
        latitude,
    )

    return CRS.from_proj4(
        f"+proj={projection} +lat_0={latitude} +lon_0={longitude} "
        "+datum=WGS84 +units=m +no_defs"
    )


def choose_measurement_crs(
    geometry: BaseGeometry,
    source_crs: CRS | None,
    family: str,
) -> CRSDecision:
    """Select the best projected CRS for measuring *geometry*.

    Parameters
    ----------
    geometry:
        The Shapely geometry to be measured.
    source_crs:
        The CRS the geometry is currently in, or ``None`` if unknown.
    family:
        ``"polygon"`` for area measurement, ``"linear"`` for length measurement.

    Returns
    -------
    CRSDecision
        Always returns a decision — check ``measurement_crs`` for ``None`` to
        detect the UNAVAILABLE case.
    """
    if source_crs is None:
        return CRSDecision(
            source_crs=None,
            measurement_crs=None,
            linear_unit=None,
            reason="A trusted source CRS is required for a reliable area/length measurement.",
        )

    source_label = crs_label(source_crs)

    # Already projected — use as-is
    if source_crs.is_projected:
        return CRSDecision(
            source_crs=source_label,
            measurement_crs=source_label,
            linear_unit=_linear_unit(source_crs),
            reason="Source CRS is already projected; measurements use its native linear unit.",
        )

    # Non-geographic, non-projected (unusual) — fall back immediately
    if not source_crs.is_geographic:
        fallback = _local_fallback_crs(geometry, family)
        fallback_label = crs_label(fallback)
        return CRSDecision(
            source_crs=source_label,
            measurement_crs=fallback_label,
            linear_unit="m",
            reason=(
                "Source CRS is neither geographic nor projected; "
                "a local metric projection was created from the feature centroid."
            ),
        )

    # Geographic CRS (e.g. EPSG:4326) — estimate optimal UTM zone
    one_feature = gpd.GeoSeries([geometry], crs=source_crs)
    utm: CRS | None = None
    try:
        utm = one_feature.estimate_utm_crs()
    except Exception as exc:
        logger.debug("UTM estimation failed: %s", exc)

    if utm is not None:
        utm_label = crs_label(utm)
        return CRSDecision(
            source_crs=source_label,
            measurement_crs=utm_label,
            linear_unit="m",
            reason="A local UTM CRS was estimated from the feature bounds.",
        )

    # UTM unavailable (e.g. near poles) — use local azimuthal fallback
    fallback = _local_fallback_crs(geometry, family)
    fallback_label = crs_label(fallback)
    return CRSDecision(
        source_crs=source_label,
        measurement_crs=fallback_label,
        linear_unit="m",
        reason=(
            "UTM estimation was unavailable (geometry may be near the poles); "
            "a local azimuthal metric CRS was created from the feature centroid."
        ),
    )
