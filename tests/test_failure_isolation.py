"""
Failure isolation tests.

Verifies that:
- A single unsupported geometry does not crash the MeasurementEngine
- The engine always returns a MeasurementResult (never raises)
- All UNSUPPORTED/FAILED results have informative messages
"""
from __future__ import annotations

import pytest
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    MultiPoint,
    Point,
)

from app.geospatial.measurement import MeasurementEngine, MeasurementResult

engine = MeasurementEngine()
GEO_CRS = CRS.from_epsg(4326)


def test_unsupported_geometry_does_not_crash():
    """GeometryCollection must return UNSUPPORTED, not raise."""
    geom = GeometryCollection([Point(0, 0)])
    result = engine.measure(geom, GEO_CRS)

    assert isinstance(result, MeasurementResult)
    assert result.status == "UNSUPPORTED"
    assert result.value is None
    assert result.message is not None


def test_none_geometry_does_not_crash():
    """None geometry must return FAILED, not raise."""
    result = engine.measure(None, GEO_CRS)

    assert isinstance(result, MeasurementResult)
    assert result.status == "FAILED"
    assert result.message is not None


def test_multipoint_does_not_crash():
    """MultiPoint must return NOT_REQUIRED, not crash."""
    geom = MultiPoint([(0, 0), (1, 1)])
    result = engine.measure(geom, GEO_CRS)

    assert result.status == "NOT_REQUIRED"
    assert result.value is None


def test_complex_geometry_collection_does_not_crash():
    """Complex GeometryCollection must not raise."""
    from shapely.geometry import LineString, Polygon

    geom = GeometryCollection(
        [
            Point(0, 0),
            LineString([(0, 0), (1, 1)]),
            Polygon([(0, 0), (1, 0), (1, 1)]),
        ]
    )
    result = engine.measure(geom, GEO_CRS)

    assert result.status == "UNSUPPORTED"
    assert isinstance(result, MeasurementResult)


def test_all_statuses_have_messages():
    """All result statuses should carry a non-empty message."""
    from shapely.geometry import LineString, Polygon

    cases = [
        (None, GEO_CRS),  # FAILED (None geometry)
        (Point(0, 0), GEO_CRS),  # NOT_REQUIRED
        (GeometryCollection([Point(0, 0)]), GEO_CRS),  # UNSUPPORTED
        (Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), None),  # UNAVAILABLE
        (Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), CRS.from_epsg(32643)),  # COMPLETED
    ]
    for geom, crs in cases:
        result = engine.measure(geom, crs)
        assert result.message is not None, f"No message for status={result.status}"
        assert len(result.message) > 5, f"Message too short for status={result.status}"
