#!/usr/bin/env python3
"""
Generate the demo Shapefile ZIP used for manual testing and documentation.

Run from the project root:
    python scripts/generate_sample_shapefile.py
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402


def generate(output_path: Path) -> None:
    geometries = [
        Polygon(
            [
                (77.5913, 12.9766),
                (77.5979, 12.9766),
                (77.5979, 12.9838),
                (77.5913, 12.9838),
                (77.5913, 12.9766),
            ]
        ),
        LineString(
            [
                (77.6080, 12.9750),
                (77.6120, 12.9750),
                (77.6160, 12.9735),
                (77.6210, 12.9720),
            ]
        ),
        Point(77.5908, 12.9793),
    ]
    names = ["Cubbon Park", "MG Road Segment", "Vidhana Soudha"]
    categories = ["park", "arterial_road", "government_building"]

    gdf = gpd.GeoDataFrame(
        {"name": names, "category": categories},
        geometry=geometries,
        crs="EPSG:4326",
    )

    shp_dir = output_path.parent / "_shp_tmp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "demo_shapefile.shp"
    gdf.to_file(shp_path, driver="ESRI Shapefile")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in shp_dir.iterdir():
            zf.write(p, arcname=p.name)

    output_path.write_bytes(buf.getvalue())
    print(f"✓ Written {output_path} ({output_path.stat().st_size} bytes, {len(gdf)} features)")

    # Clean up temp dir
    import shutil
    shutil.rmtree(shp_dir)


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    dest = root / "sample_data" / "demo_shapefile.zip"
    generate(dest)
