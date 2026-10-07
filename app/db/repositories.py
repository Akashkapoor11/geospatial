"""
Database repository layer — encapsulates all raw SQL queries.

Using a repository keeps query logic out of route handlers and makes
it easy to swap the storage backend or add caching later.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Feature, Measurement, UploadedFile


class FileRepository:
    """Data-access object for file, feature, and measurement records.

    Parameters
    ----------
    session:
        An active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Uploaded files
    # ------------------------------------------------------------------

    def get_file(self, file_id: str) -> UploadedFile | None:
        """Return the :class:`UploadedFile` with the given *file_id*, or ``None``."""
        return self.session.get(UploadedFile, file_id)

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    def count_features(self, file_id: str) -> int:
        """Return the total number of features for *file_id*."""
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Feature)
                .where(Feature.file_id == file_id)
            )
            or 0
        )

    def list_features(self, file_id: str, offset: int, limit: int) -> list[Feature]:
        """Return a page of :class:`Feature` records for *file_id*.

        Parameters
        ----------
        file_id:
            UUID of the parent uploaded file.
        offset:
            Number of records to skip (0-indexed).
        limit:
            Maximum number of records to return.
        """
        return list(
            self.session.scalars(
                select(Feature)
                .where(Feature.file_id == file_id)
                .order_by(Feature.feature_index)
                .offset(offset)
                .limit(limit)
            )
        )

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------

    def count_measurements(self, file_id: str) -> int:
        """Return the total number of measurement records for *file_id*."""
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Measurement)
                .join(Feature, Feature.id == Measurement.feature_id)
                .where(Feature.file_id == file_id)
            )
            or 0
        )

    def list_measurements(self, file_id: str, offset: int, limit: int) -> list[Measurement]:
        """Return a page of :class:`Measurement` records joined to their features.

        Results are ordered by :attr:`Feature.feature_index` for a consistent,
        predictable page order.

        Parameters
        ----------
        file_id:
            UUID of the parent uploaded file.
        offset:
            Number of records to skip (0-indexed).
        limit:
            Maximum number of records to return.
        """
        return list(
            self.session.scalars(
                select(Measurement)
                .join(Feature, Feature.id == Measurement.feature_id)
                .where(Feature.file_id == file_id)
                .order_by(Feature.feature_index)
                .offset(offset)
                .limit(limit)
            )
        )
