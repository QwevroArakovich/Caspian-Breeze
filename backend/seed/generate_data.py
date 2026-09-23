"""
Генератор seed-данных в backend/seed/data/*.geojson.

Запускается разработчиком один раз (нужен shapely: pip install shapely):
    python -m seed.generate_data

Как строятся полигоны микрорайонов (частый вопрос жюри):
  1. Берём приблизительные центры микрорайонов Актау.
  2. Строим диаграмму Вороного — каждая точка города относится к ближайшему центру,
     поэтому полигоны не пересекаются и не оставляют дыр между собой.
  3. Обрезаем ячейки по упрощённой береговой линии Каспия (море — к юго-западу)
     и кругом 750 м вокруг центра, чтобы крайние мкр не растягивались в степь.
Это модель для MVP; точные границы берутся из данных акимата / 2GIS.

Отчёты хранятся с относительным временем (days_ago, hours_ago): seed.py превращает
их в даты «за последние 30 дней» в момент запуска, поэтому демо не устаревает.
"""
import json
import math
import random
from pathlib import Path

from shapely import set_precision
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union, voronoi_diagram

DATA_DIR = Path(__file__).parent / "data"

LAT0, LON0 = 43.655, 51.170
KX = math.cos(math.radians(LAT0)) * 111_320  # метров в градусе долготы
KY = 110_540                                  # метров в градусе широты


def to_m(lat: float, lon: float) -> tuple[float, float]:
    return (lon - LON0) * KX, (lat - LAT0) * KY


def to_deg(x: float, y: float) -> tuple[float, float]:
    return round(y / KY + LAT0, 6), round(x / KX + LON0, 6)


# ── Микрорайоны: (название, lat, lon, heat_index_base, green_ratio) ─────────────
# Прибрежные (1–9) прохладнее за счёт бриза и старых посадок; внутренние и новые
# (11+, особенно 27–29) — плотная застройка, мало зелени, больше асфальта.
DISTRICTS = [
    ("1 мкр", 43.6365, 51.1700, 0.45, 0.30),
    ("2 мкр", 43.6425, 51.1620, 0.48, 0.28),
    ("3 мкр", 43.6480, 51.1560, 0.50, 0.32),
    ("4 мкр", 43.6435, 51.1780, 0.60, 0.22),
    ("5 мкр", 43.6540, 51.1500, 0.47, 0.25),
    ("6 мкр", 43.6500, 51.1700, 0.62, 0.20),
    ("7 мкр", 43.6600, 51.1470, 0.50, 0.22),
    ("8 мкр", 43.6580, 51.1620, 0.63, 0.18),
    ("9 мкр", 43.6650, 51.1580, 0.64, 0.17),
    ("11 мкр", 43.6640, 51.1750, 0.70, 0.14),
    ("12 мкр", 43.6700, 51.1680, 0.72, 0.13),
    ("14 мкр", 43.6740, 51.1600, 0.70, 0.15),
    ("27 мкр", 43.6680, 51.1950, 0.86, 0.06),
    ("28 мкр", 43.6750, 51.2000, 0.88, 0.05),
    ("29 мкр", 43.6600, 51.2050, 0.90, 0.05),
]

# Упрощённая береговая линия (с северо-запада на юго-восток); суша — к северо-востоку.
COAST = [(43.705, 51.128), (43.667, 51.1405), (43.652, 51.1425), (43.645, 51.149),
         (43.638, 51.158), (43.6325, 51.166), (43.625, 51.188)]

# ── Точки охлаждения: (название, тип, lat, lon, часы, is_verified) ───────────────
# is_verified=True — объект точно существует (координаты всё равно сверяются по 2GIS).
POINTS = [
    # Набережная / бриз
    ("Набережная Актау · 1 мкр", "embankment", 43.6355, 51.1650, "круглосуточно", True),
    ("Набережная у маяка · 5 мкр", "embankment", 43.6535, 51.1465, "круглосуточно", True),
    ("Прибрежная тропа · 3 мкр", "embankment", 43.6475, 51.1525, "круглосуточно", True),
    ("Набережная · 2 мкр", "embankment", 43.6410, 51.1570, "круглосуточно", False),
    ("Прибрежная зона · 7 мкр", "embankment", 43.6600, 51.1445, "круглосуточно", False),
    ("Прибрежная зона · 9 мкр (северная)", "embankment", 43.6680, 51.1440, "круглосуточно", False),
    # Парки и скверы
    ("Сквер у памятника Т. Шевченко", "park", 43.6495, 51.1555, "круглосуточно", True),
    ("Аллея у акимата области", "park", 43.6520, 51.1600, "круглосуточно", True),
    ("Парк Победы · Вечный огонь", "park", 43.6455, 51.1615, "круглосуточно", True),
    ("Бульвар 4 мкр", "park", 43.6430, 51.1740, "круглосуточно", False),
    ("Сквер 1 мкр", "park", 43.6380, 51.1720, "круглосуточно", False),
    ("Зелёная аллея 6 мкр", "park", 43.6495, 51.1680, "круглосуточно", False),
    ("Зелёная аллея 8 мкр", "park", 43.6570, 51.1600, "круглосуточно", False),
    ("Сквер 11 мкр", "park", 43.6630, 51.1730, "круглосуточно", False),
    ("Аллея 12 мкр", "park", 43.6710, 51.1660, "круглосуточно", False),
    ("Аллея 14 мкр", "park", 43.6750, 51.1580, "круглосуточно", False),
    ("Сквер 27 мкр (молодые посадки)", "park", 43.6690, 51.1930, "круглосуточно", False),
    # ТРЦ и библиотеки
    ("ТРЦ Aktau City Mall", "mall", 43.6745, 51.1640, "10:00–22:00", True),
    ("Торговый центр · 4 мкр", "mall", 43.6445, 51.1800, "10:00–21:00", False),
    ("Торговый центр · 11 мкр", "mall", 43.6655, 51.1770, "10:00–21:00", False),
    ("Торговый центр · 28 мкр", "mall", 43.6760, 51.1980, "10:00–21:00", False),
    ("Мангистауская областная библиотека", "library", 43.6490, 51.1640, "09:00–18:00", False),
    ("Детская библиотека · 12 мкр", "library", 43.6695, 51.1700, "09:00–18:00", False),
    # Остановки с кондиционером (демо)
    ("Остановка с кондиционером · 2 мкр", "ac_bus_stop", 43.6430, 51.1640, "06:00–23:00", False),
    ("Остановка с кондиционером · 3 мкр", "ac_bus_stop", 43.6470, 51.1590, "06:00–23:00", False),
    ("Остановка с кондиционером · 5 мкр", "ac_bus_stop", 43.6545, 51.1530, "06:00–23:00", False),
    ("Остановка с кондиционером · 6 мкр", "ac_bus_stop", 43.6505, 51.1730, "06:00–23:00", False),
    ("Остановка с кондиционером · 8 мкр", "ac_bus_stop", 43.6585, 51.1655, "06:00–23:00", False),
    ("Остановка с кондиционером · 9 мкр", "ac_bus_stop", 43.6655, 51.1610, "06:00–23:00", False),
    ("Остановка с кондиционером · 12 мкр", "ac_bus_stop", 43.6705, 51.1710, "06:00–23:00", False),
    ("Остановка с кондиционером · 14 мкр", "ac_bus_stop", 43.6735, 51.1630, "06:00–23:00", False),
    ("Остановка с кондиционером · 27 мкр", "ac_bus_stop", 43.6675, 51.1920, "06:00–23:00", False),
    ("Остановка с кондиционером · 29 мкр", "ac_bus_stop", 43.6610, 51.2020, "06:00–23:00", False),
    # Питьевые фонтанчики (демо)
    ("Фонтанчик · набережная 1 мкр", "fountain", 43.6370, 51.1640, "май–октябрь", False),
    ("Фонтанчик · сквер Шевченко", "fountain", 43.6490, 51.1550, "май–октябрь", False),
    ("Фонтанчик · парк Победы", "fountain", 43.6460, 51.1620, "май–октябрь", False),
    ("Фонтанчик · бульвар 4 мкр", "fountain", 43.6440, 51.1760, "май–октябрь", False),
    ("Фонтанчик · набережная 5 мкр", "fountain", 43.6540, 51.1475, "май–октябрь", False),
    ("Фонтанчик · 7 мкр", "fountain", 43.6605, 51.1490, "май–октябрь", False),
    ("Фонтанчик · аллея 8 мкр", "fountain", 43.6575, 51.1610, "май–октябрь", False),
    ("Фонтанчик · сквер 11 мкр", "fountain", 43.6635, 51.1740, "май–октябрь", False),
    # Аптеки: вода и помощь при тепловом ударе (демо)
    ("Аптека · 3 мкр", "pharmacy", 43.6485, 51.1580, "08:00–22:00", False),
    ("Аптека · 6 мкр", "pharmacy", 43.6510, 51.1710, "08:00–22:00", False),
    ("Аптека · 9 мкр", "pharmacy", 43.6655, 51.1600, "08:00–22:00", False),
    ("Аптека · 11 мкр", "pharmacy", 43.6645, 51.1770, "круглосуточно", False),
    ("Аптека · 14 мкр", "pharmacy", 43.6735, 51.1620, "08:00–22:00", False),
    ("Аптека · 27 мкр", "pharmacy", 43.6685, 51.1960, "08:00–22:00", False),
    ("Аптека · 28 мкр", "pharmacy", 43.6755, 51.1985, "08:00–22:00", False),
    ("Аптека · 29 мкр", "pharmacy", 43.6595, 51.2060, "круглосуточно", False),
]

REPORT_COMMENTS = {
    "no_shade": ["Длинный участок без единого навеса, днём невозможно идти",
                 "У школы нет тени, дети ждут родителей на солнце",
                 "Остановка без навеса, люди стоят на солнцепёке",
                 "Асфальтовая площадка раскаляется, деревьев нет"],
    "need_fountain": ["Детская площадка, рядом нет питьевой воды",
                      "На прогулочной дорожке нигде нельзя попить",
                      "Возле спортплощадки нужен фонтанчик"],
    "broken_ac": ["Кондиционер в павильоне остановки не включается",
                  "Павильон закрыт, внутри жарче, чем снаружи"],
    "other": ["Нет скамеек в тени у поликлиники", "Сухие деревья на аллее, нужен полив"],
}


def land_polygon() -> Polygon:
    """Суша: береговая линия + большой контур к северо-востоку (в метрах)."""
    coast = [to_m(lat, lon) for lat, lon in COAST]
    far = [to_m(43.625, 51.30), to_m(43.72, 51.30), to_m(43.72, 51.128)]
    return Polygon(coast + far)


def build_districts() -> tuple[dict, dict]:
    centers = [Point(*to_m(lat, lon)) for _, lat, lon, _, _ in DISTRICTS]
    land = land_polygon()
    cells = voronoi_diagram(MultiPoint(centers), envelope=land.buffer(5000))
    features, shapes, taken = [], {}, []
    for (name, lat, lon, heat, green), c in zip(DISTRICTS, centers):
        cell = next(g for g in cells.geoms if g.contains(c))
        poly = cell.intersection(land).intersection(c.buffer(750, quad_segs=4))
        shapes[name] = poly
        # в градусы на сетке 1e-6 (~10 см) и вычитание уже занятого: после округления
        # у соседей не остаётся «щепок»-пересечений вдоль общей границы
        deg = Polygon([(lon_, lat_) for lat_, lon_ in (to_deg(x, y) for x, y in poly.exterior.coords)])
        deg = set_precision(deg, 1e-6)
        if taken:
            deg = set_precision(deg.difference(unary_union(taken)), 1e-6)
        if deg.geom_type != "Polygon":
            deg = max(deg.geoms, key=lambda g: g.area)
        taken.append(deg)
        ring = [[round(x, 6), round(y, 6)] for x, y in deg.exterior.coords]  # GeoJSON: [lon, lat]
        features.append({
            "type": "Feature",
            "properties": {"name": name, "green_ratio": green, "heat_index_base": heat, "population": None},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    return {"type": "FeatureCollection", "features": features}, shapes


def build_points(land: Polygon) -> dict:
    features = []
    for name, ptype, lat, lon, hours, verified in POINTS:
        if not land.contains(Point(*to_m(lat, lon))):
            raise ValueError(f"Точка в море: {name}")
        features.append({
            "type": "Feature",
            "properties": {"name": name, "type": ptype, "hours": hours, "is_verified": verified},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    return {"type": "FeatureCollection", "features": features}


def random_point_in(poly: Polygon, rng: random.Random) -> Point:
    minx, miny, maxx, maxy = poly.bounds
    while True:
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if poly.contains(p):
            return p


def build_reports(shapes: dict) -> dict:
    """42 заявки: вес района = heat³, поэтому горячие внутренние мкр получают заметно больше."""
    rng = random.Random(2026)
    names = [d[0] for d in DISTRICTS]
    weights = [d[3] ** 3 for d in DISTRICTS]
    types, type_w = list(REPORT_COMMENTS), [0.55, 0.22, 0.13, 0.10]
    features = []
    for _ in range(42):
        name = rng.choices(names, weights=weights)[0]
        rtype = rng.choices(types, weights=type_w)[0]
        days = rng.randint(0, 29)
        hours = rng.randint(1, 23)
        if days > 20:
            status = rng.choice(["done", "done", "planned", "rejected"])
        elif days > 7:
            status = rng.choice(["in_review", "planned", "done", "new"])
        else:
            status = rng.choice(["new", "new", "in_review"])
        x, y = random_point_in(shapes[name], rng).coords[0]
        lat, lon = to_deg(x, y)
        features.append({
            "type": "Feature",
            "properties": {"type": rtype, "comment": rng.choice(REPORT_COMMENTS[rtype]), "status": status,
                           "days_ago": days, "hours_ago": hours, "district_hint": name},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    districts, shapes = build_districts()
    files = {
        "districts.geojson": districts,
        "cooling_points.geojson": build_points(land_polygon()),
        "reports.geojson": build_reports(shapes),
    }
    for fname, fc in files.items():
        (DATA_DIR / fname).write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{fname}: {len(fc['features'])} объектов")


if __name__ == "__main__":
    main()
