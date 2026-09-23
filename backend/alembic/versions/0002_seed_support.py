"""Поддержка seed: reports.source и уникальное имя точки охлаждения

Revision ID: 0002_seed_support
Revises: 0001_initial
Create Date: 2026-09-23

reports.source отличает демо-заявки (seed) от настоящих (form, coolpath):
seed.py может пересоздать только демо, не трогая заявки жителей.
Уникальное имя точки позволяет seed.py обновлять точки по имени (upsert).
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_seed_support"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("source", sa.String(16), nullable=False, server_default="form"))
    op.create_check_constraint("ck_reports_source", "reports", "source IN ('seed', 'form', 'coolpath')")
    op.create_index("ix_reports_source", "reports", ["source"])
    op.create_unique_constraint("uq_cooling_points_name", "cooling_points", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_cooling_points_name", "cooling_points", type_="unique")
    op.drop_index("ix_reports_source", table_name="reports")
    op.drop_constraint("ck_reports_source", "reports", type_="check")
    op.drop_column("reports", "source")
