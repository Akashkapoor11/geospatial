"""
CRS selection unit tests.

Tests cover the choose_measurement_crs() decision tree:
- Unknown CRS → measurement_crs is None
- Already-projected → measurement_crs == source_crs
- Geographic (EPSG:4326) → UTM estimated, measurement_crs != EPSG:4326
- UTM fallback logic (indirectly tested via measurement engine)
"""
from __future__ import annotations

import pytest
from pyproj import CRS
from shapely.geometry import LineString, Point, Polygon

from app.geospatial.crs import CRSDecision, choose_measurement_crs, crs_label


# ---------------------------------------------------------------------------
# crs_label helper
# ---------------------------------------------------------------------------


def test_crs_label_epsg():
    crs = CRS.from_epsg(4326)
    assert crs_label(crs) == "EPSG:4326"


def test_crs_label_none():
    assert crs_label(None) is None


def test_crs_label_projected():
    crs = CRS.from_epsg(32643)
    assert crs_label(crs) == "EPSG:32643"


# ---------------------------------------------------------------------------
# choose_measurement_crs
# ---------------------------------------------------------------------------


def test_unknown_crs_returns_none_measurement_crs():
    """When source_crs is None, measurement is not possible."""
    geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    decision = choose_measurement_crs(geom, None, "polygon")

    assert decision.measurement_crs is None
    assert decision.linear_unit is None
    assert decision.source_crs is None


def test_projected_source_crs_used_directly():
    """Projected CRS should be used as-is without reprojection."""
    geom = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    utm_crs = CRS.from_epsg(32643)
    decision = choose_measurement_crs(geom, utm_crs, "polygon")

    assert decision.measurement_crs == "EPSG:32643"
    assert decision.source_crs == "EPSG:32643"
    assert decision.linear_unit == "m"
    assert "already projected" in decision.reason.lower()


def test_geographic_crs_gets_utm_estimated():
    """Geographic input (EPSG:4326) should yield a UTM measurement CRS."""
    geom = Polygon(
        [(77.5946, 12.9716), (77.5956, 12.9716), (77.5956, 12.9726), (77.5946, 12.9726)]
    )
    geo_crs = CRS.from_epsg(4326)
    decision = choose_measurement_crs(geom, geo_crs, "polygon")

    assert decision.measurement_crs is not None
    assert decision.measurement_crs != "EPSG:4326"
    assert decision.linear_unit == "m"
    assert "utm" in decision.reason.lower()


def test_geographic_crs_linestring_gets_utm():
    """LineString in geographic CRS should also get UTM estimated."""
    geom = LineString([(77.5946, 12.9716), (77.5960, 12.9716)])
    geo_crs = CRS.from_epsg(4326)
    decision = choose_measurement_crs(geom, geo_crs, "linear")

    assert decision.measurement_crs is not None
    assert decision.measurement_crs != "EPSG:4326"
    assert decision.linear_unit == "m"


def test_decision_is_frozen_dataclass():
    """CRSDecision should be immutable."""
    geom = Point(77, 13)
    geo_crs = CRS.from_epsg(4326)
    decision = choose_measurement_crs(geom, geo_crs, "polygon")

    with pytest.raises((AttributeError, TypeError)):
        decision.measurement_crs = "EPSG:4326"  # type: ignore[misc]
