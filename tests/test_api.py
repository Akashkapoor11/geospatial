"""
End-to-end API tests covering all endpoints.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, Polygon


# ---------------------------------------------------------------------------
# Shared KML fixture bytes
# ---------------------------------------------------------------------------

DEMO_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5946,12.9716,0 77.5956,12.9716,0 77.5956,12.9726,0
              77.5946,12.9726,0 77.5946,12.9716,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Test Line</name>
      <LineString>
        <coordinates>77.5946,12.9716,0 77.5960,12.9716,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Test Point</name>
      <Point><coordinates>77.5946,12.9716,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def upload_kml(client: TestClient, kml_bytes: bytes = DEMO_KML, filename: str = "demo.kml") -> dict:
    response = client.post(
        "/api/files/",
        files={"file": (filename, kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def make_shapefile_zip(tmp_path: Path, geometry_type: str = "polygon") -> bytes:
    """Create a minimal valid Shapefile ZIP in memory."""
    gdf_data = {
        "polygon": {
            "geometry": [Polygon([(77.0, 13.0), (77.001, 13.0), (77.001, 13.001), (77.0, 13.001)])],
            "name": ["demo_polygon"],
        },
        "linestring": {
            "geometry": [LineString([(77.0, 13.0), (77.001, 13.0)])],
            "name": ["demo_line"],
        },
        "point": {
            "geometry": [Point(77.0, 13.0)],
            "name": ["demo_point"],
        },
    }
    data = gdf_data[geometry_type]
    gdf = gpd.GeoDataFrame(
        {"name": data["name"]},
        geometry=data["geometry"],
        crs="EPSG:4326",
    )
    shp_dir = tmp_path / f"shp_{geometry_type}"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "data.shp"
    gdf.to_file(shp_path, driver="ESRI Shapefile")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in shp_dir.iterdir():
            zf.write(p, arcname=p.name)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Meta / health
# ---------------------------------------------------------------------------


def test_root_returns_api_info(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "name" in body
    assert "docs" in body


def test_health_ok(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"


def test_ready_endpoint(client: TestClient):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


def test_invalid_extension_rejected(client: TestClient):
    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_without_filename_rejected(client: TestClient):
    response = client.post(
        "/api/files/",
        files={"file": ("", b"data", "application/octet-stream")},
    )
    assert response.status_code in {415, 422}


# ---------------------------------------------------------------------------
# KML upload and full pipeline
# ---------------------------------------------------------------------------


def test_upload_kml_returns_202(client: TestClient):
    body = upload_kml(client)
    assert body["filename"] == "demo.kml"
    assert body["file_type"] == "kml"
    assert body["status"] in {"UPLOADED", "PROCESSING", "COMPLETED"}
    assert "id" in body


def test_kml_processing_completes(client: TestClient):
    file_id = upload_kml(client)["id"]
    info = client.get(f"/api/files/{file_id}/").json()
    assert info["status"] == "COMPLETED"
    assert info["feature_count"] == 3
    assert info["crs"] == "EPSG:4326"


def test_kml_measurements_all_geometry_types(client: TestClient):
    file_id = upload_kml(client)["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    assert body["total"] == 3

    by_type = {item["geometry_type"]: item for item in body["items"]}

    # Polygon — area in m²
    polygon = by_type["Polygon"]
    assert polygon["measurement_type"] == "area"
    assert polygon["measurement"] > 0
    assert polygon["unit"] == "m²"
    assert polygon["measurement_crs"].startswith("EPSG:")
    assert polygon["measurement_crs"] != "EPSG:4326"  # must have been projected
    assert polygon["status"] == "COMPLETED"

    # LineString — length in m
    line = by_type["LineString"]
    assert line["measurement_type"] == "length"
    assert line["measurement"] > 0
    assert line["unit"] == "m"
    assert line["status"] == "COMPLETED"

    # Point — no measurement
    point = by_type["Point"]
    assert point["status"] == "NOT_REQUIRED"
    assert point["measurement"] is None
    assert point["measurement_type"] is None


def test_kml_measurements_paginated(client: TestClient):
    file_id = upload_kml(client)["id"]

    page1 = client.get(f"/api/files/{file_id}/measurements/?page=1&page_size=2").json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 3

    page2 = client.get(f"/api/files/{file_id}/measurements/?page=2&page_size=2").json()
    assert len(page2["items"]) == 1

    # No overlap
    ids1 = {i["feature_id"] for i in page1["items"]}
    ids2 = {i["feature_id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# Shapefile ZIP upload
# ---------------------------------------------------------------------------


def test_shapefile_zip_upload_and_measurement(client: TestClient, tmp_path: Path):
    zip_bytes = make_shapefile_zip(tmp_path, "polygon")
    response = client.post(
        "/api/files/",
        files={"file": ("survey.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 202
    file_id = response.json()["id"]

    info = client.get(f"/api/files/{file_id}/").json()
    assert info["status"] == "COMPLETED"
    assert info["feature_count"] == 1
    assert info["crs"] == "EPSG:4326"

    measurements = client.get(f"/api/files/{file_id}/measurements/").json()
    assert measurements["total"] == 1
    item = measurements["items"][0]
    assert item["measurement_type"] == "area"
    assert item["measurement"] > 0
    assert item["unit"] == "m²"


def test_shapefile_linestring_measurement(client: TestClient, tmp_path: Path):
    zip_bytes = make_shapefile_zip(tmp_path, "linestring")
    response = client.post(
        "/api/files/",
        files={"file": ("roads.zip", zip_bytes, "application/zip")},
    )
    file_id = response.json()["id"]
    measurements = client.get(f"/api/files/{file_id}/measurements/").json()
    item = measurements["items"][0]
    assert item["measurement_type"] == "length"
    assert item["measurement"] > 0
    assert item["unit"] == "m"


def test_shapefile_point_no_measurement(client: TestClient, tmp_path: Path):
    zip_bytes = make_shapefile_zip(tmp_path, "point")
    response = client.post(
        "/api/files/",
        files={"file": ("points.zip", zip_bytes, "application/zip")},
    )
    file_id = response.json()["id"]
    measurements = client.get(f"/api/files/{file_id}/measurements/").json()
    item = measurements["items"][0]
    assert item["status"] == "NOT_REQUIRED"
    assert item["measurement"] is None


# ---------------------------------------------------------------------------
# Features endpoint
# ---------------------------------------------------------------------------


def test_features_endpoint_returns_geometry_and_properties(client: TestClient):
    file_id = upload_kml(client)["id"]
    body = client.get(f"/api/files/{file_id}/features/").json()
    assert body["total"] == 3
    assert body["items"][0]["geometry"] is not None
    assert "Name" in body["items"][0]["properties"]
    assert body["items"][0]["source_crs"] == "EPSG:4326"


def test_features_paginated(client: TestClient):
    file_id = upload_kml(client)["id"]
    page1 = client.get(f"/api/files/{file_id}/features/?page=1&page_size=2").json()
    page2 = client.get(f"/api/files/{file_id}/features/?page=2&page_size=2").json()
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 1
    assert page1["total"] == 3


def test_single_feature_endpoint(client: TestClient):
    file_id = upload_kml(client)["id"]
    features = client.get(f"/api/files/{file_id}/features/").json()
    feature_id = features["items"][0]["id"]

    response = client.get(f"/api/files/{file_id}/features/{feature_id}/")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == feature_id
    assert body["geometry"] is not None


def test_single_feature_not_found(client: TestClient):
    file_id = upload_kml(client)["id"]
    response = client.get(f"/api/files/{file_id}/features/999999/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------


def test_list_files_empty(client: TestClient):
    body = client.get("/api/files/").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_files_after_upload(client: TestClient):
    upload_kml(client)
    upload_kml(client)
    body = client.get("/api/files/").json()
    assert body["total"] >= 2


def test_list_files_pagination(client: TestClient):
    for _ in range(3):
        upload_kml(client)
    page1 = client.get("/api/files/?page=1&page_size=2").json()
    assert len(page1["items"]) == 2


def test_list_files_status_filter(client: TestClient):
    upload_kml(client)
    body = client.get("/api/files/?status=COMPLETED").json()
    assert all(item["status"] == "COMPLETED" for item in body["items"])


# ---------------------------------------------------------------------------
# File info
# ---------------------------------------------------------------------------


def test_unknown_file_returns_404(client: TestClient):
    missing = str(uuid.uuid4())
    assert client.get(f"/api/files/{missing}/").status_code == 404


def test_measurements_not_found_returns_404(client: TestClient):
    missing = str(uuid.uuid4())
    assert client.get(f"/api/files/{missing}/measurements/").status_code == 404


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------


def test_delete_file(client: TestClient):
    file_id = upload_kml(client)["id"]

    # Should be findable
    assert client.get(f"/api/files/{file_id}/").status_code == 200

    # Delete
    response = client.delete(f"/api/files/{file_id}/")
    assert response.status_code == 204

    # Should now be gone
    assert client.get(f"/api/files/{file_id}/").status_code == 404


def test_delete_unknown_file_returns_404(client: TestClient):
    response = client.delete(f"/api/files/{uuid.uuid4()}/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Measurements not-ready guard
# ---------------------------------------------------------------------------


def test_measurements_returns_correct_total(client: TestClient):
    file_id = upload_kml(client)["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    # total should match feature_count
    info = client.get(f"/api/files/{file_id}/").json()
    assert body["total"] == info["feature_count"]
