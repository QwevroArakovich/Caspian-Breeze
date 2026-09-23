"""
Модели БД. Допустимые значения «перечислений» хранятся как TEXT + CHECK:
так проще добавлять новые типы (одна миграция на CHECK), чем менять PostgreSQL ENUM.
Геометрия — PostGIS, SRID 4326 (WGS 84, как у карт и GPS).
"""
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, false, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

COOLING_TYPES = ("mall", "ac_bus_stop", "park", "embankment", "fountain", "pharmacy", "library")
REPORT_TYPES = ("no_shade", "need_fountain", "broken_ac", "other")
REPORT_STATUSES = ("new", "in_review", "planned", "done", "rejected")
REPORT_SOURCES = ("seed", "form", "coolpath")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class District(Base):
    __tablename__ = "districts"
    __table_args__ = (
        CheckConstraint("green_ratio BETWEEN 0 AND 1", name="ck_districts_green_ratio"),
        CheckConstraint("heat_index_base BETWEEN 0 AND 1", name="ck_districts_heat_index_base"),
        Index("ix_districts_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False)
    population: Mapped[int | None] = mapped_column(Integer)
    green_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    heat_index_base: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    cooling_points: Mapped[list["CoolingPoint"]] = relationship(back_populates="district")
    reports: Mapped[list["Report"]] = relationship(back_populates="district")


class CoolingPoint(Base):
    __tablename__ = "cooling_points"
    __table_args__ = (
        CheckConstraint(_in("type", COOLING_TYPES), name="ck_cooling_points_type"),
        UniqueConstraint("name", name="uq_cooling_points_name"),
        Index("ix_cooling_points_geom", "geom", postgresql_using="gist"),
        Index("ix_cooling_points_type", "type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    hours: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))

    district: Mapped[District | None] = relationship(back_populates="cooling_points")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(_in("type", REPORT_TYPES), name="ck_reports_type"),
        CheckConstraint(_in("status", REPORT_STATUSES), name="ck_reports_status"),
        CheckConstraint(_in("source", REPORT_SOURCES), name="ck_reports_source"),
        Index("ix_reports_geom", "geom", postgresql_using="gist"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_district_id", "district_id"),
        Index("ix_reports_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", server_default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    photo_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="form", server_default="form")

    district: Mapped[District | None] = relationship(back_populates="reports")
    status_log: Mapped[list["ReportStatusLog"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="ReportStatusLog.changed_at"
    )


class ReportStatusLog(Base):
    __tablename__ = "report_status_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status: Mapped[str | None] = mapped_column(String(16))
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    report: Mapped[Report] = relationship(back_populates="status_log")
