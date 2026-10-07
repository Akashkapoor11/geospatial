"""
Shapefile ZIP reader tests.

Verifies that:
- A valid Shapefile ZIP is read into a GeoDataFrame correctly
- CRS is preserved
- Feature count and geometry types are correct
- Properties are carried through
- A Shapefile with projected CRS is also handled
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from app.core.config import Settings
from app.geospatial.reader import GeospatialFileReader


def _make_reader(tmp_path: Path) -> GeospatialFileReader:
    return GeospatialFileReader(
        Settings(storage_root=tmp_path / "storage", auto_create_db=True)
    )


def _write_shapefile_zip(gdf: gpd.GeoDataFrame, zip_path: Path, stem: str = "demo") -> None:
    """Helper: write GeoDataFrame to a Shapefile ZIP."""
    shp_dir = zip_path.parent / "_src"
    shp_dir.mkdir(exist_ok=True)
    gdf.to_file(shp_dir / f"{stem}.shp", driver="ESRI Shapefile")
    with zipfile.ZipFile(zip_path, "w") as archive:
        for p in shp_dir.iterdir():
            archive.write(p, arcname=p.name)


# ---------------------------------------------------------------------------
# Basic reading
# ---------------------------------------------------------------------------


def test_shapefile_zip_polygon_read(tmp_path: Path):
    """A valid polygon Shapefile ZIP is read into a GeoDataFrame."""
    gdf = gpd.GeoDataFrame(
        {"name": ["demo"]},
        geometry=[Polygon([(77.0, 13.0), (77.001, 13.0), (77.001, 13.001), (77.0, 13.001)])],
        crs="EPSG:4326",
    )
    zip_path = tmp_path / "demo.zip"
    _write_shapefile_zip(gdf, zip_path)

    reader = _make_reader(tmp_path)
    result = reader.read(zip_path, "shapefile_zip", "test-file-id")

    assert result.file_type == "shapefile_zip"
    assert len(result.geo_dataframe) == 1
    assert result.geo_dataframe.crs.to_epsg() == 4326
    assert result.geo_dataframe.geometry.iloc[0].geom_type == "Polygon"


def test_shapefile_zip_preserves_properties(tmp_path: Path):
    """Feature properties (non-geometry columns) must survive the read."""
    gdf = gpd.GeoDataFrame(
        {"name": ["Cubbon Park"], "category": ["park"], "area_ha": [120]},
        geometry=[Polygon([(77.0, 13.0), (77.001, 13.0), (77.001, 13.001), (77.0, 13.001)])],
        crs="EPSG:4326",
    )
    zip_path = tmp_path / "props.zip"
    _write_shapefile_zip(gdf, zip_path, stem="props")

    reader = _make_reader(tmp_path)
    result = reader.read(zip_path, "shapefile_zip", "test-props")

    row = result.geo_dataframe.iloc[0]
    assert row["name"] == "Cubbon Park"
    assert row["category"] == "park"


def test_shapefile_zip_linestring(tmp_path: Path):
    """LineString features are read correctly."""
    gdf = gpd.GeoDataFrame(
        {"road": ["MG Road"]},
        geometry=[LineString([(77.6, 12.97), (77.62, 12.97)])],
        crs="EPSG:4326",
    )
    zip_path = tmp_path / "line.zip"
    _write_shapefile_zip(gdf, zip_path, stem="line")

    reader = _make_reader(tmp_path)
    result = reader.read(zip_path, "shapefile_zip", "test-line")

    assert len(result.geo_dataframe) == 1
    assert result.geo_dataframe.geometry.iloc[0].geom_type == "LineString"


def test_shapefile_zip_projected_crs(tmp_path: Path):
    """Shapefile with a projected CRS (UTM) preserves the CRS."""
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:32643",
    )
    zip_path = tmp_path / "utm.zip"
    _write_shapefile_zip(gdf, zip_path, stem="utm")

    reader = _make_reader(tmp_path)
    result = reader.read(zip_path, "shapefile_zip", "test-utm")

    assert result.geo_dataframe.crs.to_epsg() == 32643


def test_shapefile_zip_multiple_features(tmp_path: Path):
    """All features are read when the Shapefile contains multiple rows."""
    polys = [
        Polygon([(i, i), (i + 1, i), (i + 1, i + 1), (i, i + 1)]) for i in range(5)
    ]
    gdf = gpd.GeoDataFrame(
        {"idx": list(range(5))},
        geometry=polys,
        crs="EPSG:4326",
    )
    zip_path = tmp_path / "multi.zip"
    _write_shapefile_zip(gdf, zip_path, stem="multi")

    reader = _make_reader(tmp_path)
    result = reader.read(zip_path, "shapefile_zip", "test-multi")

    assert len(result.geo_dataframe) == 5
