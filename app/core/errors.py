"""
Application exception hierarchy.

All custom exceptions inherit from ``AppError`` so callers can catch the
entire family with a single ``except AppError`` clause when needed.

Exception types
---------------
``UnsupportedFileError``
    Raised when an uploaded file has an extension not in the allow-list,
    or is missing a filename entirely.

``InvalidArchiveError``
    Raised when a ZIP archive fails security validation (path traversal,
    bomb, symlinks, missing sidecars, etc.).

``GeospatialProcessingError``
    Raised when the geospatial file cannot be parsed or a measurement
    calculation fails unexpectedly.

``FileNotReadyError``
    Raised when a resource that depends on completed processing is
    accessed before the background job has finished.
"""
from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""


class UnsupportedFileError(AppError):
    """The uploaded file type is not supported or the filename is missing."""


class InvalidArchiveError(AppError):
    """The ZIP archive failed security or structural validation."""


class GeospatialProcessingError(AppError):
    """The geospatial file could not be parsed or measured."""


class FileNotReadyError(AppError):
    """A resource was accessed before background processing completed."""
