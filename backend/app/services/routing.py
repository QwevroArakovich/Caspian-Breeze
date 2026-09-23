"""
CoolPath — «прохладный маршрут».

Почему такой алгоритм, а не полноценный граф с тенями (ответ жюри)
------------------------------------------------------------------
Полноценный граф требует карты тени каждого тротуара по часам (высоты зданий, кроны деревьев,
положение солнца), а таких данных по Актау нет, и за хакатон их не собрать. Поэтому мы берём
надёжную пешеходную геометрию у OSRM (граф улиц OpenStreetMap) и решаем другую, посильную
задачу: из нескольких реальных маршрутов, включая вариант с заходом в точку охлаждения,
выбираем тот, где меньше тепловая нагрузка. Оценка прозрачна (нагрев района × близость тени/бриза ×
текущая жара) и улучшается сама, когда появятся данные: достаточно заменить heat_index_base
на спутниковую температуру поверхности — алгоритм менять не придётся.

Шаги
----
1. OSRM (profile foot, alternatives=true) → 1–3 варианта.
2. Вариант через точку охлаждения, ближайшую к середине кратчайшего пути (waypoint).
3. Для каждого: линия режется на отрезки ~50 м (PostGIS ST_Segmentize по geography),
   вес отрезка = heat_index_base района × (1 − бонус тени/бриза в радиусе 100 м),
   среднее по длине × коэффициент текущей жары → heat_exposure 0..100.
4. Рекомендуем вариант с минимальным heat_exposure (меньше всего солнца на каждом метре) среди тех,
   что длиннее кратчайшего не более чем на 30 %: прохлада важнее, но крюк ограничен.
   heat_load = heat_exposure × минуты / 10 — «доза жары» за всю дорогу, для справки в интерфейсе.
"""
import json
from dataclasses import dataclass, field

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings

WALK_M_PER_MIN = 75.0          # 4,5 км/ч
MAX_DETOUR = 1.30              # рекомендованный не длиннее кратчайшего более чем на 30 %
SEGMENT_M = 50                 # длина отрезка для оценки
STRAIGHT_FACTOR = 1.25         # запасной режим без OSRM: по улицам длиннее, чем по прямой
DEFAULT_HEAT = 0.75            # вне микрорайонов (степь, промзона) — жарко

# Бонус «прохлады» у точки в радиусе 100 м: насколько снижается нагрев отрезка
RELIEF = {"embankment": 0.45, "park": 0.40, "ac_bus_stop": 0.30}
WAYPOINT_TYPES = tuple(RELIEF)


@dataclass
class RawRoute:
    coords: list[tuple[float, float]]  # [(lon, lat), …] — порядок GeoJSON
    distance_m: float
    source: str                        # osrm | straight
    label: str
    kind: str                          # shortest | alternative | via_cooling
    via: dict | None = None


@dataclass
class Evaluated:
    raw: RawRoute
    duration_min: float
    heat_exposure: float
    shade_share_pct: float
    heat_load: float
    rest_stops: list[dict] = field(default_factory=list)
    hottest: dict | None = None


def heat_factor(feels_like: float | None) -> float:
    """Коэффициент текущей жары: 18 °C → 0,35 (минимум), 40 °C → 1,0, 46 °C+ → 1,3."""
    if feels_like is None:
        return 1.0
    return max(0.35, min(1.3, (feels_like - 18) / 22))


# ── Геометрия маршрутов ──────────────────────────────────────────────────────
def osrm_routes(points: list[tuple[float, float]], alternatives: bool) -> list[dict]:
    """points — [(lat, lon), …]. Пустой список, если OSRM недоступен или не нашёл путь."""
    base = get_settings().osrm_url.rstrip("/")
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    try:
        resp = httpx.get(
            f"{base}/route/v1/foot/{path}",
            params={"overview": "full", "geometries": "geojson",
                    "alternatives": "3" if alternatives else "false"},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    if data.get("code") != "Ok":
        return []
    return [{"coords": [tuple(c) for c in r["geometry"]["coordinates"]], "distance": r["distance"]}
            for r in data.get("routes", [])]


def straight_route(points: list[tuple[float, float]], db: Session) -> tuple[list[tuple[float, float]], float]:
    coords = [(lon, lat) for lat, lon in points]
    length = db.execute(text("SELECT ST_Length(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)::geography)"),
                        {"g": json.dumps({"type": "LineString", "coordinates": coords})}).scalar()
    return coords, length * STRAIGHT_FACTOR


def pick_waypoint(line: list[tuple[float, float]], start: tuple, end: tuple, db: Session) -> dict | None:
    """Точка тени/бриза/остановки, ближайшая к середине пути (KNN-индекс PostGIS), не у самых концов."""
    row = db.execute(text("""
        WITH l AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326) AS g),
             mid AS (SELECT ST_LineInterpolatePoint(g, 0.5) AS m FROM l)
        SELECT c.id, c.name, c.type, ST_Y(c.geom) AS lat, ST_X(c.geom) AS lon
        FROM cooling_points c, mid
        WHERE c.type = ANY(:types)
          AND NOT ST_DWithin(c.geom::geography, ST_SetSRID(ST_MakePoint(:slon, :slat), 4326)::geography, 150)
          AND NOT ST_DWithin(c.geom::geography, ST_SetSRID(ST_MakePoint(:elon, :elat), 4326)::geography, 150)
        ORDER BY c.geom <-> mid.m
        LIMIT 1
    """), {"g": json.dumps({"type": "LineString", "coordinates": line}), "types": list(WAYPOINT_TYPES),
           "slat": start[0], "slon": start[1], "elat": end[0], "elon": end[1]}).mappings().first()
    return dict(row) if row else None


def build_candidates(start: tuple, end: tuple, db: Session) -> list[RawRoute]:
    candidates: list[RawRoute] = []
    found = osrm_routes([start, end], alternatives=True)
    if found:
        for i, r in enumerate(found[:3]):
            candidates.append(RawRoute(r["coords"], r["distance"], "osrm",
                                       "Кратчайший" if i == 0 else f"Альтернатива {i}",
                                       "shortest" if i == 0 else "alternative"))
    else:
        coords, dist = straight_route([start, end], db)
        candidates.append(RawRoute(coords, dist, "straight", "Кратчайший", "shortest"))

    via = pick_waypoint(candidates[0].coords, start, end, db)
    if via:
        waypoint = (via["lat"], via["lon"])
        via_found = osrm_routes([start, waypoint, end], alternatives=False)
        if via_found:
            coords, dist, source = via_found[0]["coords"], via_found[0]["distance"], "osrm"
        else:
            (coords, dist), source = straight_route([start, waypoint, end], db), "straight"
        candidates.append(RawRoute(coords, dist, source, f"Через «{via['name']}»", "via_cooling", via))
    return candidates


# ── Тепловая оценка (PostGIS) ────────────────────────────────────────────────
SEGMENTS_SQL = text("""
WITH line AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326) AS g),
seg AS (
    SELECT (ST_DumpSegments(ST_Segmentize(g::geography, :seg_m)::geometry)).geom AS s FROM line
),
pts AS (
    SELECT ST_LineInterpolatePoint(s, 0.5) AS mid, ST_Length(s::geography) AS len FROM seg
)
SELECT p.len,
       ST_Y(p.mid) AS lat, ST_X(p.mid) AS lon,
       d.heat, d.name AS district,
       COALESCE(r.relief, 0) AS relief
FROM pts p
LEFT JOIN LATERAL (
    SELECT dd.heat_index_base AS heat, dd.name FROM districts dd
    WHERE ST_DWithin(dd.geom::geography, p.mid::geography, 300)
    ORDER BY dd.geom <-> p.mid LIMIT 1
) d ON true
LEFT JOIN LATERAL (
    SELECT max(CASE c.type WHEN 'embankment' THEN :r_emb WHEN 'park' THEN :r_park
                           WHEN 'ac_bus_stop' THEN :r_stop END) AS relief
    FROM cooling_points c
    WHERE c.type = ANY(:types) AND ST_DWithin(c.geom::geography, p.mid::geography, 100)
) r ON true
""")

REST_STOPS_SQL = text("""
WITH line AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326) AS g)
SELECT c.id, c.name, c.type, ST_Y(c.geom) AS lat, ST_X(c.geom) AS lon,
       round((ST_LineLocatePoint(line.g, c.geom) * ST_Length(line.g::geography))::numeric) AS at_m
FROM cooling_points c, line
WHERE ST_DWithin(c.geom::geography, line.g::geography, 100)
ORDER BY at_m
""")


def evaluate(route: RawRoute, factor: float, db: Session) -> Evaluated:
    g = json.dumps({"type": "LineString", "coordinates": route.coords})
    rows = db.execute(SEGMENTS_SQL, {"g": g, "seg_m": SEGMENT_M, "types": list(WAYPOINT_TYPES),
                                     "r_emb": RELIEF["embankment"], "r_park": RELIEF["park"],
                                     "r_stop": RELIEF["ac_bus_stop"]}).mappings().all()
    total = sum(r["len"] for r in rows) or 1.0
    weighted, shaded, hottest = 0.0, 0.0, None
    for r in rows:
        heat = r["heat"] if r["heat"] is not None else DEFAULT_HEAT
        value = heat * (1 - r["relief"])
        weighted += value * r["len"]
        if r["relief"] > 0:
            shaded += r["len"]
        if hottest is None or value > hottest[0]:
            hottest = (value, {"lat": round(r["lat"], 6), "lon": round(r["lon"], 6),
                               "district_name": r["district"]})
    exposure = min(100.0, weighted / total * factor * 100)
    duration = route.distance_m / WALK_M_PER_MIN
    stops = [dict(s) | {"at_m": float(s["at_m"])} for s in db.execute(REST_STOPS_SQL, {"g": g}).mappings()]
    return Evaluated(
        raw=route, duration_min=round(duration, 1), heat_exposure=round(exposure, 1),
        shade_share_pct=round(100 * shaded / total, 1), heat_load=round(exposure * duration / 10, 1),
        rest_stops=stops, hottest=hottest[1] if hottest else None,
    )


def _is_duplicate(a: Evaluated, b: Evaluated) -> bool:
    return (abs(a.raw.distance_m - b.raw.distance_m) < 0.02 * max(a.raw.distance_m, 1)
            and abs(a.heat_exposure - b.heat_exposure) < 1.0)


def cool_routes(start: tuple, end: tuple, feels_like: float | None, db: Session) -> dict:
    factor = heat_factor(feels_like)
    evaluated: list[Evaluated] = []
    for cand in build_candidates(start, end, db):
        ev = evaluate(cand, factor, db)
        if not any(_is_duplicate(ev, x) for x in evaluated):
            evaluated.append(ev)

    shortest = min(evaluated, key=lambda e: e.raw.distance_m)
    allowed = [e for e in evaluated if e.raw.distance_m <= shortest.raw.distance_m * MAX_DETOUR]
    best = min(allowed, key=lambda e: (e.heat_exposure, e.raw.distance_m))

    gain_pct = 0.0 if best is shortest or shortest.heat_exposure == 0 else \
        round(100 * (shortest.heat_exposure - best.heat_exposure) / shortest.heat_exposure)
    extra_min = round(best.duration_min - shortest.duration_min)
    if best is shortest or gain_pct <= 0:
        summary = "Кратчайший путь здесь и самый прохладный."
    else:
        summary = f"На {gain_pct:.0f} % меньше солнца, +{max(extra_min, 0)} мин"
    return {"evaluated": evaluated, "best": best, "shortest": shortest, "factor": factor,
            "comparison": {"heat_less_pct": max(gain_pct, 0), "extra_min": max(extra_min, 0), "text": summary}}
