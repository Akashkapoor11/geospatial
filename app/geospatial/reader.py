"""
Geospatial file reader — KML and Shapefile ZIP ingestion.

Security hardening for ZIP archives
-------------------------------------
- Path-traversal check (``..`` and absolute paths rejected)
- Encrypted entry detection
- Symlink entry rejection (via ``external_attr`` mode bits)
- Maximum entry count limit (``MAX_ZIP_ENTRIES``)
- Maximum uncompressed-size limit (``MAX_ZIP_UNCOMPRESSED_MB``)
- Duplicate entry name detection
- Exactly-one-Shapefile enforcement
- Required sidecar validation (``.shp``, ``.shx``, ``.dbf``)
"""
from __future__ import annotations

import logging
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import geopandas as gpd

from app.core.config import Settings
from app.core.errors import GeospatialProcessingError, InvalidArchiveError, UnsupportedFileError

logger = logging.getLogger(__name__)

# Minimum sidecar files required alongside the .shp
REQUIRED_SIDECARS = frozenset({".shp", ".shx", ".dbf"})

# Supported file extensions and their internal type labels
_EXTENSION_MAP: dict[str, str] = {
    ".kml": "kml",
    ".zip": "shapefile_zip",
}


@dataclass(frozen=True)
class ReadResult:
    """Holds the parsed GeoDataFrame and the detected file type."""

    geo_dataframe: gpd.GeoDataFrame
    file_type: str


class GeospatialFileReader:
    """Reads KML files and Shapefile ZIP archives into a :class:`~geopandas.GeoDataFrame`.

    Parameters
    ----------
    settings:
        Application settings (used for ZIP size/entry limits and storage root).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def detect_type(filename: str) -> str:
        """Return the file-type label for *filename*, or raise :exc:`UnsupportedFileError`.

        Parameters
        ----------
        filename:
            The original upload filename including extension.

        Returns
        -------
        str
            One of ``"kml"`` or ``"shapefile_zip"``.

        Raises
        ------
        UnsupportedFileError
            If the extension is not in the allow-list.
        """
        suffix = Path(filename).suffix.lower()
        file_type = _EXTENSION_MAP.get(suffix)
        if file_type is None:
            allowed = ", ".join(sorted(_EXTENSION_MAP))
            raise UnsupportedFileError(
                f"Unsupported file extension '{suffix}'. "
                f"Allowed extensions: {allowed}."
            )
        return file_type

    def read(self, path: Path, file_type: str, file_id: str) -> ReadResult:
        """Read a geospatial file from *path* into a GeoDataFrame.

        Parameters
        ----------
        path:
            Absolute path to the uploaded file on disk.
        file_type:
            One of ``"kml"`` or ``"shapefile_zip"``.
        file_id:
            UUID of the upload record (used to name the extraction directory).

        Returns
        -------
        ReadResult

        Raises
        ------
        GeospatialProcessingError
            If the file cannot be parsed.
        UnsupportedFileError
            If *file_type* is not recognised.
        InvalidArchiveError
            If the ZIP fails security validation.
        """
        if file_type == "kml":
            return self._read_kml(path)

        if file_type == "shapefile_zip":
            return self._read_shapefile_zip(path, file_id)

        raise UnsupportedFileError(f"Unsupported file type: '{file_type}'.")

    # ------------------------------------------------------------------
    # Private readers
    # ------------------------------------------------------------------

    def _read_kml(self, path: Path) -> ReadResult:
        """Parse a KML file, handling multi-layer KML gracefully."""
        gdf: gpd.GeoDataFrame | None = None

        # Attempt multi-layer KML read (requires pyogrio ≥ 0.9 / geopandas ≥ 1.0).
        # If list_layers is unavailable or the file has a single unnamed layer,
        # fall through to the standard single-layer read below.
        try:
            layers = gpd.list_layers(path)
            if layers is not None and len(layers) > 0:
                for layer_name in layers["name"]:
                    try:
                        candidate = gpd.read_file(path, layer=layer_name, engine="pyogrio")
                        if len(candidate) > 0:
                            gdf = candidate
                            logger.debug(
                                "KML: reading layer '%s' (%d features)", layer_name, len(candidate)
                            )
                            break
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("gpd.list_layers failed (%s); falling back to default read", exc)

        # Default single-layer read (covers most KML files)
        if gdf is None:
            try:
                gdf = gpd.read_file(path, engine="pyogrio")
            except Exception as exc:
                raise GeospatialProcessingError(f"Unable to read KML: {exc}") from exc

        return ReadResult(self._normalize(gdf), "kml")

    def _read_shapefile_zip(self, path: Path, file_id: str) -> ReadResult:
        """Extract a Shapefile ZIP securely and parse the .shp file."""
        extraction_root = path.parent / f"{file_id}_extracted"
        extraction_root.mkdir(parents=True, exist_ok=True)
        shp_path = self._safe_extract_shapefile(path, extraction_root)

        try:
            gdf = gpd.read_file(shp_path, engine="pyogrio")
        except Exception as exc:
            raise GeospatialProcessingError(f"Unable to read Shapefile: {exc}") from exc

        return ReadResult(self._normalize(gdf), "shapefile_zip")

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Ensure the GeoDataFrame has an active geometry column named ``geometry``."""
        if "geometry" not in gdf.columns and gdf.geometry is None:
            raise GeospatialProcessingError("The dataset does not contain a geometry column.")

        # Some drivers return the geometry column under a different name.
        if gdf.geometry.name != "geometry":
            gdf = gdf.set_geometry(gdf.geometry.name)

        return gdf

    # ------------------------------------------------------------------
    # Secure ZIP extraction
    # ------------------------------------------------------------------

    def _safe_extract_shapefile(self, zip_path: Path, destination: Path) -> Path:
        """Extract *zip_path* to *destination* after thorough security validation.

        Returns the path to the extracted ``.shp`` file.

        Raises
        ------
        InvalidArchiveError
            On any security or structural violation.
        """
        if not zipfile.is_zipfile(zip_path):
            raise InvalidArchiveError("Uploaded .zip file is not a valid ZIP archive.")

        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()

            # ── Entry count guard ──────────────────────────────────────
            if len(infos) > self.settings.max_zip_entries:
                raise InvalidArchiveError(
                    f"ZIP contains too many entries "
                    f"(found {len(infos)}, limit {self.settings.max_zip_entries})."
                )

            # ── Per-entry validation ───────────────────────────────────
            total_uncompressed = 0
            seen_names: set[str] = set()

            for info in infos:
                # Uncompressed size bomb guard
                total_uncompressed += max(0, info.file_size)
                if total_uncompressed > self.settings.max_zip_uncompressed_bytes:
                    raise InvalidArchiveError(
                        f"ZIP uncompressed content exceeds the "
                        f"{self.settings.max_zip_uncompressed_mb} MB limit."
                    )

                # Normalise path separators
                archive_name = info.filename.replace("\\", "/")
                normalized = PurePosixPath(archive_name)

                # Duplicate entry names
                if archive_name in seen_names:
                    raise InvalidArchiveError(
                        f"ZIP contains duplicate entry name: '{archive_name}'."
                    )
                seen_names.add(archive_name)

                # Path-traversal check
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise InvalidArchiveError(
                        f"ZIP contains an unsafe path: '{archive_name}'."
                    )

                # Encrypted entries
                if info.flag_bits & 0x1:
                    raise InvalidArchiveError(
                        "Encrypted ZIP entries are not supported."
                    )

                # Symlink entries (via Unix mode bits in external_attr)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise InvalidArchiveError(
                        f"ZIP contains a symbolic-link entry: '{archive_name}'."
                    )

            # ── Shapefile structure validation ─────────────────────────
            shp_entries = [
                info.filename
                for info in infos
                if info.filename.lower().endswith(".shp")
            ]
            if not shp_entries:
                raise InvalidArchiveError(
                    "ZIP does not contain a .shp file. "
                    "Ensure the archive includes the Shapefile and its sidecars."
                )
            if len(shp_entries) > 1:
                raise InvalidArchiveError(
                    "ZIP must contain exactly one Shapefile; "
                    f"found {len(shp_entries)}: {shp_entries}."
                )

            shp_entry = shp_entries[0]
            base = os.path.splitext(shp_entry)[0]
            siblings = {info.filename.lower() for info in infos}

            for sidecar in REQUIRED_SIDECARS:
                expected = f"{base}{sidecar}".lower()
                if expected not in siblings:
                    raise InvalidArchiveError(
                        f"Shapefile is incomplete; missing required component: "
                        f"'{base}{sidecar}'."
                    )

            # ── Safe extraction ────────────────────────────────────────
            logger.debug(
                "Extracting %d entries from ZIP to %s", len(infos), destination
            )
            for info in infos:
                target = destination / PurePosixPath(info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)

        return destination / PurePosixPath(shp_entry)
