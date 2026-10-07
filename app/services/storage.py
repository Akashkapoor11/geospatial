"""
File storage service — streaming upload, size validation, and disk cleanup.

Responsibilities
----------------
- Validate the filename and extension before writing anything to disk.
- Stream the upload to a UUID-keyed directory to avoid filename collisions.
- Enforce the ``MAX_UPLOAD_SIZE_MB`` limit during streaming (not after).
- Delete the upload directory (including extracted Shapefile dirs) on request.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import UnsupportedFileError
from app.geospatial.reader import GeospatialFileReader

logger = logging.getLogger(__name__)


class FileStorageService:
    """Manages file persistence for uploaded geospatial files.

    Parameters
    ----------
    settings:
        Application settings providing storage root path and size limits.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def save_upload(self, upload: UploadFile) -> tuple[str, str, int, Path]:
        """Stream *upload* to disk after validating the filename and extension.

        Parameters
        ----------
        upload:
            The FastAPI ``UploadFile`` from the multipart form.

        Returns
        -------
        (file_id, safe_filename, total_bytes, stored_path)

        Raises
        ------
        UnsupportedFileError
            If the filename is missing, contains a null byte, has an
            unsupported extension, or exceeds ``MAX_UPLOAD_SIZE_MB``.
        """
        if not upload.filename:
            raise UnsupportedFileError("Uploaded file must have a filename.")
        if "\x00" in upload.filename:
            raise UnsupportedFileError("Filename contains an invalid null byte.")

        # Raises UnsupportedFileError for unsupported extensions
        GeospatialFileReader.detect_type(upload.filename)

        file_id = str(uuid4())
        safe_name = Path(upload.filename).name  # strip any directory components
        target_dir = self.settings.storage_root / "uploads" / file_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name

        total_bytes = 0
        try:
            with target_path.open("wb") as output:
                while True:
                    chunk = await upload.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > self.settings.max_upload_size_bytes:
                        target_path.unlink(missing_ok=True)
                        raise UnsupportedFileError(
                            f"Uploaded file exceeds the "
                            f"{self.settings.max_upload_size_mb} MB limit. "
                            "Please upload a smaller file."
                        )
                    output.write(chunk)
        finally:
            await upload.close()

        logger.info(
            "Saved upload file_id=%s filename=%s bytes=%d path=%s",
            file_id,
            safe_name,
            total_bytes,
            target_path,
        )
        return file_id, safe_name, total_bytes, target_path

    def delete_stored_file(self, stored_path: str) -> None:
        """Remove the upload directory for a file.

        The directory contains the uploaded file and any extracted Shapefile
        components. Deletion is best-effort: errors are logged but not raised,
        so a missing directory does not fail a DELETE request.

        Parameters
        ----------
        stored_path:
            The absolute path to the stored file (not the directory). The
            parent directory (``<uuid>/``) is removed recursively.
        """
        try:
            path = Path(stored_path)
            # stored_path points to the file itself; remove its UUID parent directory
            upload_dir = path.parent
            if upload_dir.exists():
                shutil.rmtree(upload_dir, ignore_errors=True)
                logger.info("Deleted upload directory: %s", upload_dir)
            else:
                logger.debug("Upload directory already absent: %s", upload_dir)
        except Exception:
            logger.exception("Failed to delete stored file at %s", stored_path)
