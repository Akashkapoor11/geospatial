"""
Security tests for the ZIP archive extraction pipeline.

Verifies that the GeospatialFileReader rejects:
- ZIP path traversal (``..`` in entry names)
- Duplicate entry names
- Multiple Shapefile entries
- Missing required sidecar files
- Upload size limit
"""
from __future__ import annotations

import io
from pathlib import Path
from warnings import catch_warnings, simplefilter
from zipfile import ZipFile

import pytest

from app.core.config import Settings
from app.core.errors import InvalidArchiveError, UnsupportedFileError
from app.geospatial.reader import GeospatialFileReader


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_root=tmp_path / "storage",
        auto_create_db=True,
        max_zip_entries=50,
        max_zip_uncompressed_mb=10,
        max_upload_size_mb=1,
    )


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------


def test_zip_path_traversal_rejected(tmp_path: Path):
    """``../escape.txt`` entries must be rejected."""
    zip_path = tmp_path / "evil.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape.txt", "boom")
        archive.writestr("data.shp", b"not-real")
        archive.writestr("data.shx", b"not-real")
        archive.writestr("data.dbf", b"not-real")

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="unsafe path"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


def test_zip_absolute_path_rejected(tmp_path: Path):
    """Absolute paths inside ZIP must be rejected."""
    zip_path = tmp_path / "absolute.zip"
    buf = io.BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr("/etc/passwd", "root")
        archive.writestr("data.shp", b"not-real")
        archive.writestr("data.shx", b"not-real")
        archive.writestr("data.dbf", b"not-real")
    zip_path.write_bytes(buf.getvalue())

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="unsafe path"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


# ---------------------------------------------------------------------------
# Duplicate names
# ---------------------------------------------------------------------------


def test_duplicate_zip_entry_names_rejected(tmp_path: Path):
    """Duplicate entry names indicate a malformed or malicious archive."""
    zip_path = tmp_path / "duplicate.zip"
    with catch_warnings():
        simplefilter("ignore", UserWarning)
        with ZipFile(zip_path, "w") as archive:
            archive.writestr("demo.shp", b"fake")
            archive.writestr("demo.shp", b"fake-again")
            archive.writestr("demo.shx", b"fake")
            archive.writestr("demo.dbf", b"fake")

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="duplicate entry"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


# ---------------------------------------------------------------------------
# Multiple Shapefiles
# ---------------------------------------------------------------------------


def test_multiple_shapefiles_rejected(tmp_path: Path):
    """A ZIP with more than one .shp file must be rejected."""
    zip_path = tmp_path / "multiple.zip"
    with ZipFile(zip_path, "w") as archive:
        for base in ["a", "b"]:
            archive.writestr(f"{base}.shp", b"fake")
            archive.writestr(f"{base}.shx", b"fake")
            archive.writestr(f"{base}.dbf", b"fake")

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="exactly one Shapefile"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


# ---------------------------------------------------------------------------
# Missing sidecars
# ---------------------------------------------------------------------------


def test_missing_shx_rejected(tmp_path: Path):
    """ZIP missing the .shx sidecar must be rejected."""
    zip_path = tmp_path / "missing_shx.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("data.shp", b"fake")
        # .shx intentionally omitted
        archive.writestr("data.dbf", b"fake")

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="missing required component"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


def test_missing_dbf_rejected(tmp_path: Path):
    """ZIP missing the .dbf sidecar must be rejected."""
    zip_path = tmp_path / "missing_dbf.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("data.shp", b"fake")
        archive.writestr("data.shx", b"fake")
        # .dbf intentionally omitted

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match="missing required component"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


def test_no_shp_file_rejected(tmp_path: Path):
    """ZIP with no .shp file at all must be rejected."""
    zip_path = tmp_path / "no_shp.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("readme.txt", "hello")

    reader = GeospatialFileReader(_make_settings(tmp_path))
    with pytest.raises(InvalidArchiveError, match=".shp"):
        reader._safe_extract_shapefile(zip_path, tmp_path / "extract")


# ---------------------------------------------------------------------------
# Extension allow-list
# ---------------------------------------------------------------------------


def test_detect_type_kml():
    assert GeospatialFileReader.detect_type("survey.kml") == "kml"


def test_detect_type_zip():
    assert GeospatialFileReader.detect_type("data.zip") == "shapefile_zip"


def test_detect_type_unsupported():
    with pytest.raises(UnsupportedFileError, match="Unsupported file extension"):
        GeospatialFileReader.detect_type("malware.exe")


def test_detect_type_case_insensitive():
    """Extension detection must be case-insensitive."""
    assert GeospatialFileReader.detect_type("DATA.ZIP") == "shapefile_zip"
    assert GeospatialFileReader.detect_type("Survey.KML") == "kml"


# ---------------------------------------------------------------------------
# API-level upload size rejection
# ---------------------------------------------------------------------------


def test_upload_size_limit_rejected(client):
    """Uploading a file larger than MAX_UPLOAD_SIZE_MB must return 415."""
    # conftest sets max_upload_size_mb=5; send 6 MB of zeros
    big_kml_content = b"<kml>" + b"x" * (6 * 1024 * 1024) + b"</kml>"
    response = client.post(
        "/api/files/",
        files={"file": ("big.kml", big_kml_content, "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 415
    assert "limit" in response.json()["detail"].lower()


def test_not_a_zip_file_rejected(client, tmp_path: Path):
    """A .zip extension with non-ZIP content must be rejected."""
    response = client.post(
        "/api/files/",
        files={"file": ("fake.zip", b"not a zip", "application/zip")},
    )
    # Either rejected at upload (415) or fails during processing (FAILED status)
    if response.status_code == 202:
        file_id = response.json()["id"]
        info = client.get(f"/api/files/{file_id}/").json()
        assert info["status"] == "FAILED"
    else:
        assert response.status_code == 415
