from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import REPORT_STATUSES, District, Report, ReportStatusLog
from app.schemas import (Feature, FeatureCollection, ReportCreate, ReportProps, StatusChange, StatusLogEntry,
                         point)

router = APIRouter(prefix="/api/reports", tags=["reports"])

OPEN_STATUSES = ("new", "in_review", "planned")
# Вес точки на тепловой карте: нерешённые проблемы горят ярче, выполненные — слабый след, отклонённые не видны
HEAT_WEIGHTS = {"new": 1.0, "in_review": 1.0, "planned": 0.7, "done": 0.2, "rejected": 0.0}

# Район заявки: полигон, в который попала точка (ST_Contains). Если точка на стыке или у кромки
# полигона (границы мкр упрощённые) — ближайший микрорайон в пределах 1,5 км.
DISTRICT_FOR_POINT_SQL = text("""
SELECT COALESCE(
  (SELECT id FROM districts WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1),
  (SELECT id FROM districts
    WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 1500)
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1)
)
""")


def _report_select():
    return (
        select(Report.id, Report.type, Report.comment, Report.status, Report.source, Report.district_id,
               District.name.label("district_name"), Report.created_at, Report.updated_at, Report.photo_url,
               func.ST_X(Report.geom).label("lon"), func.ST_Y(Report.geom).label("lat"))
        .outerjoin(District, District.id == Report.district_id)
    )


def _history(db: Session, report_id: int) -> list[StatusLogEntry]:
    rows = db.execute(
        select(ReportStatusLog).where(ReportStatusLog.report_id == report_id)
        .order_by(ReportStatusLog.changed_at, ReportStatusLog.id)
    ).scalars()
    return [StatusLogEntry(old_status=r.old_status, new_status=r.new_status, note=r.note, changed_at=r.changed_at)
            for r in rows]


def _to_feature(r, history: list[StatusLogEntry] | None = None) -> Feature[ReportProps]:
    return Feature[ReportProps](
        id=r.id, geometry=point(r.lon, r.lat),
        properties=ReportProps(type=r.type, comment=r.comment, status=r.status, source=r.source,
                               district_id=r.district_id, district_name=r.district_name,
                               created_at=r.created_at, updated_at=r.updated_at, photo_url=r.photo_url,
                               history=history),
    )


def _get_feature(db: Session, report_id: int, with_history: bool = True) -> Feature[ReportProps]:
    row = db.execute(_report_select().where(Report.id == report_id)).first()
    if row is None:
        raise HTTPException(404, detail=f"Заявка №{report_id} не найдена")
    return _to_feature(row, _history(db, report_id) if with_history else None)


@router.get("/heatmap", response_model=list[tuple[float, float, float]])
def heatmap(
    db: Session = Depends(get_db),
    days: Annotated[int, Query(ge=1, le=365, description="за сколько последних дней")] = 30,
):
    """Точки для тепловой карты обращений: [lat, lon, weight]."""
    rows = db.execute(
        select(func.ST_Y(Report.geom), func.ST_X(Report.geom), Report.status)
        .where(Report.created_at >= func.now() - func.make_interval(0, 0, 0, days))
        .where(Report.status != "rejected")
    )
    return [(round(lat, 6), round(lon, 6), HEAT_WEIGHTS[s]) for lat, lon, s in rows]


@router.get("", response_model=FeatureCollection[ReportProps])
def list_reports(
    db: Session = Depends(get_db),
    status_: Annotated[list[str] | None, Query(alias="status", description="можно несколько: ?status=new&status=planned "
                                                                          "или через запятую")] = None,
    district_id: int | None = None,
    date_from: Annotated[datetime | None, Query(alias="from", description="ISO-дата или дата-время")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
):
    """Заявки жителей с фильтрами (новые сверху)."""
    stmt = _report_select().order_by(Report.created_at.desc()).limit(limit)
    if status_:
        statuses = [s.strip() for raw in status_ for s in raw.split(",") if s.strip()]
        bad = [s for s in statuses if s not in REPORT_STATUSES]
        if bad:
            raise HTTPException(422, detail=f"Неизвестный статус: {', '.join(bad)}")
        stmt = stmt.where(Report.status.in_(statuses))
    if district_id is not None:
        stmt = stmt.where(Report.district_id == district_id)
    if date_from:
        stmt = stmt.where(Report.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Report.created_at <= date_to)
    return FeatureCollection[ReportProps](features=[_to_feature(r) for r in db.execute(stmt)])


@router.get("/{report_id}", response_model=Feature[ReportProps])
def get_report(report_id: int, db: Session = Depends(get_db)):
    """Одна заявка с историей статусов — для страницы «Моя заявка»."""
    return _get_feature(db, report_id)


@router.post("", response_model=Feature[ReportProps], status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    """Новая заявка жителя. Микрорайон определяется автоматически по координатам."""
    district_id = db.execute(DISTRICT_FOR_POINT_SQL, {"lat": payload.lat, "lon": payload.lon}).scalar()
    report = Report(
        type=payload.type, comment=(payload.comment or "").strip() or None,
        geom=func.ST_SetSRID(func.ST_MakePoint(payload.lon, payload.lat), 4326),
        district_id=district_id, status="new", source=payload.source,
    )
    db.add(report)
    db.flush()
    db.add(ReportStatusLog(report_id=report.id, old_status=None, new_status="new", note="Заявка создана"))
    db.commit()
    return _get_feature(db, report.id)


@router.patch("/{report_id}/status", response_model=Feature[ReportProps], dependencies=[Depends(require_admin)])
def change_status(report_id: int, payload: StatusChange, db: Session = Depends(get_db)):
    """Смена статуса диспетчером акимата (заголовок X-Admin-Token). Каждое изменение пишется в историю."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(404, detail=f"Заявка №{report_id} не найдена")
    old = report.status
    report.status = payload.status
    report.updated_at = func.now()
    db.add(ReportStatusLog(report_id=report_id, old_status=old, new_status=payload.status,
                           note=(payload.note or "").strip() or None))
    db.commit()
    return _get_feature(db, report_id)
