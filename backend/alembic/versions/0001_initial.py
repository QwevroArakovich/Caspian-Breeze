"""Начальная схема: districts, cooling_points, reports, report_status_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

COOLING_TYPES = "'mall', 'ac_bus_stop', 'park', 'embankment', 'fountain', 'pharmacy', 'library'"
REPORT_TYPES = "'no_shade', 'need_fountain', 'broken_ac', 'other'"
REPORT_STATUSES = "'new', 'in_review', 'planned', 'done', 'rejected'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "districts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("geom", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("population", sa.Integer),
        sa.Column("green_ratio", sa.Float, nullable=False),
        sa.Column("heat_index_base", sa.Float, nullable=False),
        sa.CheckConstraint("green_ratio BETWEEN 0 AND 1", name="ck_districts_green_ratio"),
        sa.CheckConstraint("heat_index_base BETWEEN 0 AND 1", name="ck_districts_heat_index_base"),
    )
    op.create_index("ix_districts_geom", "districts", ["geom"], postgresql_using="gist")

    op.create_table(
        "cooling_points",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("hours", sa.Text),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("district_id", sa.Integer, sa.ForeignKey("districts.id", ondelete="SET NULL")),
        sa.CheckConstraint(f"type IN ({COOLING_TYPES})", name="ck_cooling_points_type"),
    )
    op.create_index("ix_cooling_points_geom", "cooling_points", ["geom"], postgresql_using="gist")
    op.create_index("ix_cooling_points_type", "cooling_points", ["type"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("district_id", sa.Integer, sa.ForeignKey("districts.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("photo_url", sa.Text),
        sa.CheckConstraint(f"type IN ({REPORT_TYPES})", name="ck_reports_type"),
        sa.CheckConstraint(f"status IN ({REPORT_STATUSES})", name="ck_reports_status"),
    )
    op.create_index("ix_reports_geom", "reports", ["geom"], postgresql_using="gist")
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_district_id", "reports", ["district_id"])

    op.create_table(
        "report_status_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_status", sa.String(16)),
        sa.Column("new_status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_report_status_log_report_id", "report_status_log", ["report_id"])


def downgrade() -> None:
    op.drop_table("report_status_log")
    op.drop_table("reports")
    op.drop_table("cooling_points")
    op.drop_table("districts")
