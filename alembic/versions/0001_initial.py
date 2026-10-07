"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("source_crs", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_files_status", "uploaded_files", ["status"])

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("feature_index", sa.Integer(), nullable=False),
        sa.Column("geometry_type", sa.String(length=64), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("source_crs", sa.String(length=512), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("validity_issue", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_features_file_id", "features", ["file_id"])

    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("measurement_type", sa.String(length=32), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("measurement_crs", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("geometry_repaired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_id"),
    )
    op.create_index("ix_measurements_feature_id", "measurements", ["feature_id"])


def downgrade() -> None:
    op.drop_index("ix_measurements_feature_id", table_name="measurements")
    op.drop_table("measurements")
    op.drop_index("ix_features_file_id", table_name="features")
    op.drop_table("features")
    op.drop_index("ix_uploaded_files_status", table_name="uploaded_files")
    op.drop_table("uploaded_files")
