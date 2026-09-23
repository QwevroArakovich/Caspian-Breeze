"""Панель диспетчера акимата. Все эндпоинты требуют заголовок X-Admin-Token."""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import REPORT_STATUSES, REPORT_TYPES
from app.schemas import AdminSummary
from app.services.districts import district_stats
from app.services.recommend import recommend
from app.services import weather as weather_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

AKTAU_TZ = timezone(timedelta(hours=5))
TYPE_RU = {"no_shade": "Нет тени / навеса", "need_fountain": "Нужна питьевая вода",
           "broken_ac": "Не работает кондиционер", "other": "Другое"}
STATUS_RU = {"new": "Новая", "in_review": "На рассмотрении", "planned": "Запланировано",
             "done": "Выполнено", "rejected": "Отклонено"}
SOURCE_RU = {"seed": "демо", "form": "форма", "coolpath": "маршрут CoolPath"}


@router.get("/check")
def check():
    """Проверка токена при входе в панель."""
    return {"ok": True}


@router.get("/summary", response_model=AdminSummary)
def summary(db: Session = Depends(get_db)):
    """KPI, рейтинг микрорайонов с рекомендациями и данные для графиков (последние 30 дней)."""
    stats = district_stats(db)
    ratings = []
    for r in stats:
        by_type = {"no_shade": r["open_no_shade"], "need_fountain": r["open_need_fountain"],
                   "broken_ac": r["open_broken_ac"], "other": r["open_other"]}
        ratings.append({
            "id": r["id"], "name": r["name"], "shade_deficit_index": r["shade_deficit_index"],
            "index_components": r["index_components"], "open_reports": r["open_reports"], "open_by_type": by_type,
            "cooling_points": r["cooling_points"], "cooling_density_km2": round(r["cooling_density_km2"], 2),
            "green_ratio": r["green_ratio"],
            "recommendation": recommend(r["shade_deficit_index"], by_type["no_shade"],
                                        by_type["need_fountain"], by_type["broken_ac"]),
        })
    ratings.sort(key=lambda x: x["shade_deficit_index"], reverse=True)

    counts = db.execute(text("""
        SELECT count(*) FILTER (WHERE status IN ('new', 'in_review', 'planned')) AS open,
               count(*) FILTER (WHERE created_at >= now() - interval '7 days') AS d7,
               count(*) FILTER (WHERE created_at >= now() - interval '14 days'
                                  AND created_at < now() - interval '7 days') AS prev7
        FROM reports
    """)).mappings().one()

    # По дням в часовом поясе Актау, с нулями для дней без заявок
    daily = db.execute(text("""
        SELECT to_char(day, 'YYYY-MM-DD') AS date, count(r.id) AS count
        FROM generate_series((now() AT TIME ZONE 'Asia/Aqtau')::date - 29,
                             (now() AT TIME ZONE 'Asia/Aqtau')::date, interval '1 day') AS day
        LEFT JOIN reports r ON (r.created_at AT TIME ZONE 'Asia/Aqtau')::date = day::date
        GROUP BY day ORDER BY day
    """)).mappings().all()
    by_type = db.execute(text("""
        SELECT type, count(*) AS count FROM reports
        WHERE created_at >= now() - interval '30 days' GROUP BY type ORDER BY count DESC
    """)).mappings().all()

    avg = sum(r["shade_deficit_index"] for r in ratings) / len(ratings) if ratings else 0.0
    return {
        "kpi": {
            "open_reports": counts["open"], "avg_deficit_index": round(avg, 1),
            "reports_7d": counts["d7"], "reports_prev_7d": counts["prev7"],
            "top_districts": [{k: r[k] for k in ("id", "name", "shade_deficit_index", "open_reports")}
                              for r in ratings[:3]],
        },
        "districts": ratings,
        "daily": [dict(d) for d in daily],
        "by_type": [dict(t) for t in by_type],
        "generated_at": datetime.now(AKTAU_TZ).replace(microsecond=0),
    }


@router.get("/reports.csv")
def export_csv(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None, description="через запятую: new,in_review"),
    district_id: int | None = None,
    type: str | None = Query(default=None, description="через запятую: no_shade,need_fountain"),
):
    """CSV для отдела благоустройства: UTF-8 с BOM и разделителем «;» — открывается в Excel без настройки."""
    where, params = ["1=1"], {}
    if status:
        statuses = [s for s in status.split(",") if s]
        if any(s not in REPORT_STATUSES for s in statuses):
            raise HTTPException(422, detail="Неизвестный статус")
        where.append("r.status = ANY(:statuses)")
        params["statuses"] = statuses
    if type:
        types = [t for t in type.split(",") if t]
        if any(t not in REPORT_TYPES for t in types):
            raise HTTPException(422, detail="Неизвестный тип")
        where.append("r.type = ANY(:types)")
        params["types"] = types
    if district_id is not None:
        where.append("r.district_id = :district_id")
        params["district_id"] = district_id

    rows = db.execute(text(f"""
        SELECT r.id, r.created_at, r.updated_at, d.name AS district, r.type, r.status, r.comment, r.source,
               ST_Y(r.geom) AS lat, ST_X(r.geom) AS lon,
               (SELECT l.note FROM report_status_log l WHERE l.report_id = r.id AND l.note IS NOT NULL AND l.old_status IS NOT NULL
                 ORDER BY l.changed_at DESC, l.id DESC LIMIT 1) AS last_note
        FROM reports r LEFT JOIN districts d ON d.id = r.district_id
        WHERE {' AND '.join(where)}
        ORDER BY r.created_at DESC
    """), params).mappings().all()

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM: Excel сразу понимает UTF-8 и кириллицу
    w = csv.writer(buf, delimiter=";")
    w.writerow(["№", "Создана", "Обновлена", "Микрорайон", "Тип", "Статус", "Комментарий жителя",
                "Последний комментарий акимата", "Источник", "Широта", "Долгота", "Ссылка на 2GIS"])
    fmt = lambda dt: dt.astimezone(AKTAU_TZ).strftime("%d.%m.%Y %H:%M")  # noqa: E731
    for r in rows:
        w.writerow([r["id"], fmt(r["created_at"]), fmt(r["updated_at"]), r["district"] or "",
                    TYPE_RU.get(r["type"], r["type"]), STATUS_RU.get(r["status"], r["status"]), r["comment"] or "",
                    r["last_note"] or "", SOURCE_RU.get(r["source"], r["source"]),
                    f"{r['lat']:.6f}", f"{r['lon']:.6f}",
                    f"https://2gis.kz/aktau/geo/{r['lon']:.6f},{r['lat']:.6f}"])
    filename = f"caspian_breeze_reports_{datetime.now(AKTAU_TZ):%Y%m%d_%H%M}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/demo/reset")
def demo_reset(db: Session = Depends(get_db)):
    """
    Демо-режим для повторных прогонов питча: удаляет ВСЕ заявки (и жителей, и демо) с историей,
    заново создаёт 42 демо-заявки со свежими датами, обновляет микрорайоны и точки из seed-файлов.
    На реальном внедрении эндпоинт отключается (DEMO_RESET_ENABLED=false).
    """
    from app.config import get_settings
    from seed.seed import seed_cooling_points, seed_districts, seed_reports

    if not get_settings().demo_reset_enabled:
        raise HTTPException(403, detail="Сброс демо-данных отключён на этом сервере")
    removed = db.execute(text("DELETE FROM reports WHERE source <> 'seed'")).rowcount
    seed_districts(db)
    seed_cooling_points(db)
    created = seed_reports(db, reset=True)
    db.commit()
    weather_service.clear_cache()
    return {"removed_user_reports": removed, "demo_reports": created}
