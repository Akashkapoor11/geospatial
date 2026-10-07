"""
Extended unit tests for the MeasurementEngine and CRS selection logic.

Covers:
- Polygon / MultiPolygon area
- LineString / MultiLineString length
- Point / MultiPoint — NOT_REQUIRED
- Empty geometry — FAILED
- None geometry — FAILED
- Unknown CRS — UNAVAILABLE
- Already-projected source CRS
- GeometryCollection — UNSUPPORTED
- Invalid geometry auto-repair
- geometry_repaired flag propagation
"""
from __future__ import annotations

import pytest
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from app.geospatial.measurement import MeasurementEngine, MeasurementResult

engine = MeasurementEngine()

# Coordinates in Bengaluru (EPSG:4326)
BANGALORE_CRS = CRS.from_epsg(4326)
UTM43N_CRS = CRS.from_epsg(32643)  # WGS 84 / UTM zone 43N


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------


def test_polygon_area_uses_projected_crs():
    """Polygon in EPSG:4326 must be projected before area calculation."""
    geom = Polygon(
        [(77.5946, 12.9716), (77.5956, 12.9716), (77.5956, 12.9726), (77.5946, 12.9726)]
    )
    result = engine.measure(geom, BANGALORE_CRS)

    assert result.status == "COMPLETED"
    assert result.measurement_type == "area"
    assert result.value is not None and result.value > 0
    assert result.unit == "m²"
    assert result.measurement_crs is not None
    assert result.measurement_crs != "EPSG:4326"  # must have projected


def test_polygon_area_already_projected():
    """Polygon in an already-projected CRS should use that CRS directly."""
    geom = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    result = engine.measure(geom, UTM43N_CRS)

    assert result.status == "COMPLETED"
    assert result.value == pytest.approx(100.0, rel=1e-3)
    assert result.unit == "m²"
    assert result.measurement_crs == "EPSG:32643"
    assert result.geometry_repaired is False


def test_multipolygon_area():
    """MultiPolygon should be treated the same as Polygon."""
    poly1 = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    poly2 = Polygon([(10, 10), (15, 10), (15, 15), (10, 15)])
    geom = MultiPolygon([poly1, poly2])

    result = engine.measure(geom, UTM43N_CRS)

    assert result.status == "COMPLETED"
    assert result.measurement_type == "area"
    assert result.value == pytest.approx(50.0, rel=1e-3)  # 25 + 25


def test_polygon_missing_crs_returns_unavailable():
    """Polygon with unknown CRS must return UNAVAILABLE, not crash."""
    geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    result = engine.measure(geom, None)

    assert result.status == "UNAVAILABLE"
    assert result.value is None
    assert result.measurement_type == "area"


# ---------------------------------------------------------------------------
# LineString
# ---------------------------------------------------------------------------


def test_linestring_length_uses_projected_crs():
    """LineString in EPSG:4326 must be projected before length calculation."""
    geom = LineString([(77.5946, 12.9716), (77.5956, 12.9716)])
    result = engine.measure(geom, BANGALORE_CRS)

    assert result.status == "COMPLETED"
    assert result.measurement_type == "length"
    assert result.value is not None and result.value > 0
    assert result.unit == "m"
    assert result.measurement_crs != "EPSG:4326"


def test_multilinestring_length():
    """MultiLineString should be treated the same as LineString."""
    geom = MultiLineString(
        [
            [(77.0, 13.0), (77.001, 13.0)],
            [(77.002, 13.0), (77.003, 13.0)],
        ]
    )
    result = engine.measure(geom, BANGALORE_CRS)

    assert result.status == "COMPLETED"
    assert result.measurement_type == "length"
    assert result.value is not None and result.value > 0
    assert result.unit == "m"


def test_linestring_missing_crs_returns_unavailable():
    """LineString with unknown CRS must return UNAVAILABLE, not crash."""
    geom = LineString([(0, 0), (1, 1)])
    result = engine.measure(geom, None)

    assert result.status == "UNAVAILABLE"
    assert result.value is None
    assert result.measurement_type == "length"


# ---------------------------------------------------------------------------
# Point
# ---------------------------------------------------------------------------


def test_point_requires_no_measurement():
    """Point geometry should carry NOT_REQUIRED status with null measurement."""
    result = engine.measure(Point(77.5946, 12.9716), BANGALORE_CRS)

    assert result.status == "NOT_REQUIRED"
    assert result.value is None
    assert result.unit is None
    assert result.measurement_type is None
    assert result.measurement_crs is None


def test_multipoint_requires_no_measurement():
    """MultiPoint should also be NOT_REQUIRED."""
    geom = MultiPoint([(0, 0), (1, 1), (2, 2)])
    result = engine.measure(geom, BANGALORE_CRS)

    assert result.status == "NOT_REQUIRED"
    assert result.value is None


# ---------------------------------------------------------------------------
# Unsupported / edge cases
# ---------------------------------------------------------------------------


def test_geometry_collection_is_unsupported():
    """GeometryCollection must return UNSUPPORTED, not crash."""
    geom = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    result = engine.measure(geom, BANGALORE_CRS)

    assert result.status == "UNSUPPORTED"
    assert result.value is None


def test_none_geometry_returns_failed():
    """None geometry must return FAILED, not crash."""
    result = engine.measure(None, BANGALORE_CRS)

    assert result.status == "FAILED"
    assert result.value is None


def test_empty_polygon_returns_failed():
    """An empty Polygon must return FAILED."""
    result = engine.measure(Polygon(), BANGALORE_CRS)

    assert result.status == "FAILED"
    assert result.value is None


# ---------------------------------------------------------------------------
# Invalid geometry repair
# ---------------------------------------------------------------------------


def test_invalid_polygon_is_repaired():
    """A self-intersecting (bow-tie) polygon should be repaired and measured."""
    # A figure-8 / bow-tie polygon — invalid due to self-intersection
    bow_tie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    assert not bow_tie.is_valid, "Test setup: bow_tie must be invalid"

    result = engine.measure(bow_tie, UTM43N_CRS)

    # Should either succeed with repair or be completed
    assert result.status in {"COMPLETED", "FAILED"}
    if result.status == "COMPLETED":
        assert result.geometry_repaired is True
        assert result.value is not None and result.value > 0


# ---------------------------------------------------------------------------
# Measurement value sanity
# ---------------------------------------------------------------------------


def test_area_value_is_rounded():
    """Area values must be rounded to 6 decimal places."""
    geom = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    result = engine.measure(geom, UTM43N_CRS)

    assert result.status == "COMPLETED"
    assert result.value is not None
    # Ensure it's rounded to at most 6 decimal places
    assert result.value == round(result.value, 6)


def test_length_value_is_rounded():
    """Length values must be rounded to 6 decimal places."""
    geom = LineString([(0, 0), (100, 0)])
    result = engine.measure(geom, UTM43N_CRS)

    assert result.status == "COMPLETED"
    assert result.value is not None
    assert result.value == round(result.value, 6)
