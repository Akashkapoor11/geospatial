"""
Database models for the Geospatial File Measurement API.

Three tables:
  uploaded_files  — one row per upload
  features        — one row per geospatial feature extracted from a file
  measurements    — one-to-one with features, holds area/length result
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UploadedFile(Base):
    """Represents an uploaded file and its overall processing state."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)

    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_crs: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # UPLOADED → PROCESSING → COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="Feature.feature_index",
    )


class Feature(Base):
    """Represents a single geospatial feature extracted from an uploaded file."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_crs: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validity_issue: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[UploadedFile] = relationship(back_populates="features")
    measurement: Mapped["Measurement | None"] = relationship(
        back_populates="feature",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Measurement(Base):
    """Stores the area/length measurement result for a single feature."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    measurement_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry_repaired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    feature: Mapped[Feature] = relationship(back_populates="measurement")
