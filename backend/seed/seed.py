"""
Наполнение БД данными Актау из backend/seed/data/*.geojson.

Запуск (из папки backend/):
    python -m seed.seed                  # идемпотентно: можно запускать сколько угодно раз
    python -m seed.seed --reset-reports  # пересоздать демо-заявки со свежими датами

Что делает:
  • микрорайоны и точки охлаждения — upsert по имени (повторный запуск обновляет, не дублирует);
  • district_id точек и заявок — через PostGIS: ближайший полигон микрорайона (в пределах 1,5 км);
  • демо-заявки (source='seed') создаются, только если их ещё нет; заявки жителей
    (source='form' / 'coolpath') скрипт никогда не трогает.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CoolingPoint, District, Report, ReportStatusLog

DATA_DIR = Path(__file__).parent / "data"

STATUS_NOTES = {
    "in_review": "Передано в отдел благоустройства",
    "planned": "Включено в план установки навесов",
    "done": "Работы выполнены",
    "rejected": "Не подтвердилось при выезде на место",
}

ASSIGN_DISTRICT_SQL = """
UPDATE {table} t SET district_id = nearest.id
FROM (
    SELECT t2.id AS row_id,
           (SELECT d.id FROM districts d
             WHERE ST_DWithin(d.geom::geography, t2.geom::geography, 1500)
             ORDER BY d.geom <-> t2.geom LIMIT 1) AS id
    FROM {table} t2
    {where}
) nearest
WHERE t.id = nearest.row_id
"""


def load(name: str) -> list[dict]:
    return json.loads((DATA_DIR / f"{name}.geojson").read_text(encoding="utf-8"))["features"]


def to_geom(geometry: dict):
    return func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)


def seed_districts(db: Session) -> int:
    features = load("districts")
    for f in features:
        p = f["properties"]
        stmt = insert(District).values(
            name=p["name"], geom=to_geom(f["geometry"]), population=p.get("population"),
            green_ratio=p["green_ratio"], heat_index_base=p["heat_index_base"],
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[District.name],
            set_={
                "geom": stmt.excluded.geom,
                "green_ratio": stmt.excluded.green_ratio,
                "heat_index_base": stmt.excluded.heat_index_base,
                # население, внесённое командой вручную, не затираем пустым значением из файла
                "population": func.coalesce(stmt.excluded.population, District.population),
            },
        )
        db.execute(stmt)
    return len(features)


def seed_cooling_points(db: Session) -> int:
    features = load("cooling_points")
    for f in features:
        p = f["properties"]
        stmt = insert(CoolingPoint).values(
            name=p["name"], type=p["type"], geom=to_geom(f["geometry"]),
            hours=p.get("hours"), is_verified=p.get("is_verified", False),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cooling_points_name",
            set_={
                "type": stmt.excluded.type,
                "geom": stmt.excluded.geom,
                "hours": stmt.excluded.hours,
                # отметку «проверено», поставленную командой в БД, seed не снимает
                "is_verified": or_(CoolingPoint.is_verified, stmt.excluded.is_verified),
            },
        )
        db.execute(stmt)
    db.execute(text(ASSIGN_DISTRICT_SQL.format(table="cooling_points", where="")))
    return len(features)


def build_status_log(report_id: int, status: str, created: datetime, now: datetime) -> list[ReportStatusLog]:
    log = [ReportStatusLog(report_id=report_id, old_status=None, new_status="new",
                           note="Заявка создана", changed_at=created)]
    if status == "new":
        return log
    step = min(timedelta(days=1), (now - created) / 3)
    t, prev = created, "new"
    chain = ["in_review"] if status in ("in_review", "rejected") else ["in_review", "planned"]
    if status in ("done", "rejected"):
        chain.append(status)
    for s in chain:
        t = t + step
        log.append(ReportStatusLog(report_id=report_id, old_status=prev, new_status=s,
                                   note=STATUS_NOTES[s], changed_at=t))
        prev = s
    return log


def seed_reports(db: Session, reset: bool) -> int:
    existing = db.scalar(select(func.count()).select_from(Report).where(Report.source == "seed"))
    if existing and not reset:
        print(f"reports: демо-заявки уже есть ({existing}), пропускаю (--reset-reports чтобы пересоздать)",
              flush=True)
        return 0
    if existing:
        db.execute(delete(Report).where(Report.source == "seed"))  # лог удаляется каскадом

    now = datetime.now(timezone.utc).replace(microsecond=0)
    features = load("reports")
    for f in features:
        p = f["properties"]
        created = now - timedelta(days=p["days_ago"], hours=p["hours_ago"])
        log = build_status_log(0, p["status"], created, now)
        report = Report(
            type=p["type"], comment=p.get("comment"), geom=to_geom(f["geometry"]), status=p["status"],
            source="seed", created_at=created, updated_at=log[-1].changed_at,
        )
        db.add(report)
        db.flush()
        for entry in log:
            entry.report_id = report.id
            db.add(entry)
    db.flush()
    db.execute(text(ASSIGN_DISTRICT_SQL.format(table="reports", where="WHERE t2.source = 'seed'")))
    return len(features)


def main() -> None:
    parser = argparse.ArgumentParser(description="Наполнение БД Caspian Breeze данными Актау")
    parser.add_argument("--reset-reports", action="store_true", help="пересоздать демо-заявки со свежими датами")
    args = parser.parse_args()

    with SessionLocal() as db, db.begin():
        n_d = seed_districts(db)
        n_p = seed_cooling_points(db)
        n_r = seed_reports(db, reset=args.reset_reports)

    with SessionLocal() as db:
        orphans = db.scalar(select(func.count()).select_from(CoolingPoint).where(CoolingPoint.district_id.is_(None)))
        total_reports = db.scalar(select(func.count()).select_from(Report))
    print(f"districts: {n_d} · cooling_points: {n_p} (без микрорайона: {orphans}) · "
          f"reports добавлено: {n_r}, всего в БД: {total_reports}")


if __name__ == "__main__":
    main()
