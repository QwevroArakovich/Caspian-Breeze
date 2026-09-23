"""
Caspian Breeze — платформа теплового комфорта г. Актау (Мангистауская область).

Функции:
  • карта точек охлаждения и зон перегрева (индекс дефицита тени по микрорайонам);
  • CoolPath — выбор пешего маршрута с наименьшей тепловой нагрузкой;
  • заявки жителей («нет тени», «нужен фонтанчик», «сломан кондиционер»);
  • панель диспетчера акимата: KPI, тепловая карта обращений, смена статусов, экспорт CSV.

Запуск:
  pip install -r requirements.txt
  streamlit run app.py

Переменные окружения (необязательно):
  CB_DB_PATH      — путь к SQLite-базе (по умолчанию caspian_breeze.db)
  CB_ADMIN_TOKEN  — токен диспетчера акимата (по умолчанию aktau2026)
"""

import math
import os
import random
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("CB_DB_PATH", "caspian_breeze.db")
ADMIN_TOKEN = os.getenv("CB_ADMIN_TOKEN", "aktau2026")
AKTAU_CENTER = (43.660, 51.170)
AKTAU_TZ = timezone(timedelta(hours=5))
WALK_SPEED_KMH = 4.5
SAMPLE_STEP_M = 40.0
MAX_DETOUR = 1.30  # рекомендованный маршрут может быть длиннее кратчайшего максимум на 30 %

LAYERS = {
    "ac": {"label": "Кондиционируемые остановки и ТРЦ", "emoji": "❄️"},
    "water": {"label": "Питьевая вода", "emoji": "💧"},
    "shade": {"label": "Тенистые зоны", "emoji": "🌳"},
    "breeze": {"label": "Набережная / бриз", "emoji": "🌊"},
}

# Насколько точка охлаждения снижает тепловую нагрузку: (радиус действия, м; сила 0..1)
RELIEF = {
    "breeze": (300, 0.45),
    "shade": (150, 0.40),
    "ac": (90, 0.30),
    "water": (60, 0.10),
}

REPORT_TYPES = {
    "no_shade": "Нет тени / навеса",
    "need_water": "Нужен питьевой фонтанчик",
    "broken_ac": "Не работает кондиционер на остановке",
    "hot_surface": "Раскалённое покрытие, нет зелени",
    "other": "Другое",
}

STATUSES = {
    "new": "Новая",
    "in_review": "На рассмотрении",
    "planned": "Запланирован навес / объект",
    "done": "Выполнено",
    "rejected": "Отклонено",
}
OPEN_STATUSES = ("new", "in_review", "planned")
STATUS_COLORS = {
    "new": "#D64933",
    "in_review": "#E8922E",
    "planned": "#2E7FB8",
    "done": "#3F9143",
    "rejected": "#9A9486",
}

HEAT_LEVELS = {
    "normal": ("Комфортно", "#7FB069", "Погода комфортная, ограничений нет."),
    "caution": ("Осторожно", "#E9B949", "Пейте воду каждые 30–40 минут и выбирайте теневые улицы."),
    "danger": ("Опасно", "#E8822E", "С 12:00 до 17:00 избегайте открытых участков — стройте маршрут через CoolPath."),
    "extreme": ("Экстремальная жара", "#C8412B",
                "Пожилым и детям лучше оставаться в прохладе. Маршруты — только через точки охлаждения."),
}

# Минимальная локализация ключевых подписей
T = {
    "ru": {
        "subtitle": "Карта теплового комфорта Актау: где прохладно, как дойти в тени и куда сообщить о жаре",
        "tab_map": "🗺 Карта прохлады",
        "tab_route": "🧭 CoolPath",
        "tab_report": "📣 Сообщить о проблеме",
        "tab_admin": "🏛 Диспетчер акимата",
        "feels": "ощущается как",
    },
    "kk": {
        "subtitle": "Ақтаудың жылу жайлылығы картасы: қай жер салқын, көлеңкемен қалай жетуге болады, ыстық туралы қайда хабарлау керек",
        "tab_map": "🗺 Салқындық картасы",
        "tab_route": "🧭 CoolPath",
        "tab_report": "📣 Мәселе туралы хабарлау",
        "tab_admin": "🏛 Әкімдік диспетчері",
        "feels": "сезіледі",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Seed-данные Актау.
# heat_base (0..1) и green_ratio (0..1) — модельные оценки для MVP: прибрежные
# микрорайоны охлаждаются бризом, внутренние и новые (27+) — плотная застройка,
# мало зелени, больше асфальта. Координаты приблизительные, сверяются по 2GIS.
# ──────────────────────────────────────────────────────────────────────────────
DISTRICTS_SEED = [
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
    ("15 мкр", 43.6800, 51.1650, 0.74, 0.12),
    ("17 мкр", 43.6850, 51.1750, 0.78, 0.10),
    ("27 мкр", 43.6680, 51.1950, 0.86, 0.06),
    ("28 мкр", 43.6750, 51.2000, 0.88, 0.05),
    ("29 мкр", 43.6600, 51.2050, 0.90, 0.05),
    ("31 мкр", 43.6900, 51.1900, 0.85, 0.07),
    ("32 мкр", 43.6950, 51.2050, 0.92, 0.04),
]

# (название, тип, lat, lon, описание, объект существует и проверен командой)
POINTS_SEED = [
    # ❄️ Кондиционируемые остановки и ТРЦ
    ("ТРЦ Aktau City Mall", "ac", 43.6745, 51.1640, "Кондиционер, вода, туалеты. Открыт 10:00–22:00", 1),
    ("ЦОН г. Актау — зал ожидания", "ac", 43.6560, 51.1640, "Кондиционируемый зал, кулер с водой", 1),
    ("Областная библиотека — читальный зал", "ac", 43.6490, 51.1640, "Бесплатный вход, кондиционер", 1),
    ("Остановка с кондиционером · 3 мкр", "ac", 43.6470, 51.1590, "Закрытый павильон, работает летом", 0),
    ("Остановка с кондиционером · 6 мкр", "ac", 43.6505, 51.1730, "Закрытый павильон", 0),
    ("Остановка с кондиционером · 8 мкр", "ac", 43.6585, 51.1655, "Закрытый павильон", 0),
    ("Остановка с кондиционером · 12 мкр", "ac", 43.6705, 51.1710, "Закрытый павильон", 0),
    ("Остановка с кондиционером · 15 мкр", "ac", 43.6795, 51.1680, "Закрытый павильон", 0),
    ("Остановка с кондиционером · 17 мкр", "ac", 43.6845, 51.1780, "Закрытый павильон", 0),
    ("Остановка с кондиционером · 27 мкр", "ac", 43.6675, 51.1920, "Закрытый павильон", 0),
    # 💧 Питьевая вода
    ("Фонтанчик · набережная 1 мкр", "water", 43.6370, 51.1640, "Питьевой фонтанчик", 0),
    ("Фонтанчик · сквер 3 мкр", "water", 43.6485, 51.1545, "Питьевой фонтанчик", 0),
    ("Фонтанчик · бульвар 4 мкр", "water", 43.6440, 51.1760, "Питьевой фонтанчик", 0),
    ("Фонтанчик · парк 7 мкр", "water", 43.6605, 51.1490, "Питьевой фонтанчик", 0),
    ("Аптека · 9 мкр (вода, первая помощь)", "water", 43.6655, 51.1600, "Вода, помощь при тепловом ударе", 0),
    ("Аптека · 11 мкр (вода, первая помощь)", "water", 43.6645, 51.1770, "Вода, помощь при тепловом ударе", 0),
    ("Аптека · 14 мкр (вода, первая помощь)", "water", 43.6735, 51.1620, "Вода, помощь при тепловом ударе", 0),
    ("Аптека · 28 мкр (вода, первая помощь)", "water", 43.6755, 51.1980, "Вода, помощь при тепловом ударе", 0),
    # 🌳 Тенистые зоны
    ("Сквер у памятника Т. Шевченко", "shade", 43.6495, 51.1555, "Деревья, скамейки в тени", 1),
    ("Аллея у акимата области", "shade", 43.6520, 51.1600, "Озеленённая аллея", 1),
    ("Парк Победы · Вечный огонь", "shade", 43.6455, 51.1615, "Тенистые дорожки", 1),
    ("Бульвар 4 мкр", "shade", 43.6430, 51.1740, "Аллея с деревьями", 0),
    ("Зелёная аллея 8 мкр", "shade", 43.6570, 51.1600, "Деревья вдоль дорожки", 0),
    ("Сквер 11 мкр", "shade", 43.6630, 51.1730, "Небольшой сквер", 0),
    ("Аллея 14 мкр", "shade", 43.6750, 51.1580, "Молодые посадки, частичная тень", 0),
    # 🌊 Набережная / бриз
    ("Набережная Актау · 1 мкр", "breeze", 43.6355, 51.1650, "Морской бриз, прогулочная зона", 1),
    ("Набережная у маяка · 5 мкр", "breeze", 43.6535, 51.1465, "Бриз, вид на Каспий", 1),
    ("Прибрежная тропа · 3 мкр", "breeze", 43.6470, 51.1520, "Обрывистый берег, ветер с моря", 1),
    ("Прибрежная зона · 7 мкр", "breeze", 43.6595, 51.1440, "Бриз, скамейки", 0),
]


# ──────────────────────────────────────────────────────────────────────────────
# База данных
# ──────────────────────────────────────────────────────────────────────────────
def now_aktau() -> datetime:
    return datetime.now(AKTAU_TZ).replace(microsecond=0)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def db_execute(sql: str, params: tuple = ()) -> int:
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


SCHEMA = """
CREATE TABLE IF NOT EXISTS districts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    heat_base REAL NOT NULL,
    green_ratio REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cooling_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ac','water','shade','breeze')),
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    description TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    comment TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    district_id INTEGER REFERENCES districts(id),
    status TEXT NOT NULL DEFAULT 'new',
    source TEXT NOT NULL DEFAULT 'form',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS report_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    note TEXT,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_district ON reports(district_id);
"""


def seed_reports(conn: sqlite3.Connection) -> None:
    """Демо-обращения за последние 30 дней: чаще в горячих внутренних микрорайонах."""
    rng = random.Random(42)
    districts = conn.execute("SELECT id, lat, lon, heat_base FROM districts").fetchall()
    weights = [d["heat_base"] ** 3 for d in districts]
    type_keys = list(REPORT_TYPES)
    type_weights = [0.42, 0.25, 0.12, 0.16, 0.05]
    comments = {
        "no_shade": "Длинный участок без единого навеса, днём невозможно идти",
        "need_water": "Детская площадка, рядом нет воды",
        "broken_ac": "Кондиционер в павильоне не включается",
        "hot_surface": "Асфальтовая площадка раскаляется, деревьев нет",
        "other": "Нет скамеек в тени у поликлиники",
    }
    now = now_aktau()
    for _ in range(38):
        d = rng.choices(districts, weights=weights)[0]
        rtype = rng.choices(type_keys, weights=type_weights)[0]
        age = timedelta(days=rng.randint(1, 30), hours=rng.randint(0, 23))
        created = now - age
        days = age.days
        if days > 20:
            status = rng.choice(["done", "done", "planned", "rejected"])
        elif days > 7:
            status = rng.choice(["in_review", "planned", "done", "new"])
        else:
            status = rng.choice(["new", "new", "in_review"])
        lat = d["lat"] + rng.uniform(-0.0028, 0.0028)
        lon = d["lon"] + rng.uniform(-0.0035, 0.0035)
        cur = conn.execute(
            "INSERT INTO reports (type, comment, lat, lon, district_id, status, source, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (rtype, comments[rtype], lat, lon, d["id"], status, "seed",
             created.isoformat(), (created + timedelta(days=min(days, 3))).isoformat()),
        )
        rid = cur.lastrowid
        conn.execute(
            "INSERT INTO report_status_log (report_id, old_status, new_status, note, changed_at) VALUES (?,?,?,?,?)",
            (rid, None, "new", "Заявка создана", created.isoformat()),
        )
        if status != "new":
            conn.execute(
                "INSERT INTO report_status_log (report_id, old_status, new_status, note, changed_at)"
                " VALUES (?,?,?,?,?)",
                (rid, "new", status, "Обработано диспетчером", (created + timedelta(days=min(days, 3))).isoformat()),
            )


def init_db(force_reset: bool = False) -> None:
    with closing(get_conn()) as conn, conn:
        if force_reset:
            conn.executescript(
                "DROP TABLE IF EXISTS report_status_log; DROP TABLE IF EXISTS reports;"
                "DROP TABLE IF EXISTS cooling_points; DROP TABLE IF EXISTS districts;"
            )
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM districts").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO districts (name, lat, lon, heat_base, green_ratio) VALUES (?,?,?,?,?)",
                DISTRICTS_SEED,
            )
        if conn.execute("SELECT COUNT(*) FROM cooling_points").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO cooling_points (name, type, lat, lon, description, is_verified) VALUES (?,?,?,?,?,?)",
                POINTS_SEED,
            )
        if conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0:
            seed_reports(conn)


@st.cache_resource
def bootstrap_db() -> bool:
    """Инициализация один раз на процесс сервера."""
    init_db()
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Геометрия
# ──────────────────────────────────────────────────────────────────────────────
def haversine_m(a: tuple, b: tuple) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def polyline_length(pts: list) -> float:
    return sum(haversine_m(a, b) for a, b in zip(pts, pts[1:]))


def resample(pts: list, step: float = SAMPLE_STEP_M) -> list:
    """Равномерные точки вдоль линии каждые `step` метров."""
    if len(pts) < 2:
        return list(pts)
    out, carry = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        seg = haversine_m(a, b)
        if seg == 0:
            continue
        pos = step - carry
        while pos <= seg:
            t = pos / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            pos += step
        carry = seg - (pos - step)
    out.append(pts[-1])
    return out


def nearest_district(pt: tuple, districts: pd.DataFrame) -> pd.Series:
    dists = districts.apply(lambda r: haversine_m(pt, (r["lat"], r["lon"])), axis=1)
    return districts.loc[dists.idxmin()]


# ──────────────────────────────────────────────────────────────────────────────
# Данные и аналитика
# ──────────────────────────────────────────────────────────────────────────────
def load_districts() -> pd.DataFrame:
    return db_query("SELECT * FROM districts ORDER BY id")


def load_points() -> pd.DataFrame:
    return db_query("SELECT * FROM cooling_points ORDER BY type, name")


def load_reports() -> pd.DataFrame:
    df = db_query(
        "SELECT r.*, d.name AS district FROM reports r LEFT JOIN districts d ON d.id = r.district_id "
        "ORDER BY r.created_at DESC"
    )
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["updated_at"] = pd.to_datetime(df["updated_at"])
    return df


def district_stats(districts: pd.DataFrame, points: pd.DataFrame, reports: pd.DataFrame,
                   exclude_after: datetime | None = None) -> pd.DataFrame:
    """
    Индекс дефицита тени (0..100) по микрорайону:
      0.40 · базовый нагрев (застройка, асфальт)
    + 0.25 · (1 − доля зелени)
    + 0.20 · открытые заявки жителей (нормировано по максимуму)
    + 0.15 · (1 − плотность точек охлаждения в радиусе 700 м, нормировано)
    exclude_after — посчитать индекс «как было» до указанного времени (для дельты за 24 ч).
    """
    df = districts.copy()
    rep = reports
    if not rep.empty and exclude_after is not None:
        rep = rep[rep["created_at"] < pd.Timestamp(exclude_after)]
    open_rep = rep[rep["status"].isin(OPEN_STATUSES)] if not rep.empty else rep
    df["open_reports"] = df["id"].map(open_rep.groupby("district_id").size() if not open_rep.empty else {})
    df["open_reports"] = df["open_reports"].fillna(0).astype(int)

    def density(r):
        return sum(1 for _, p in points.iterrows() if haversine_m((r["lat"], r["lon"]), (p["lat"], p["lon"])) <= 700)

    df["cool_points"] = df.apply(density, axis=1)
    rep_norm = df["open_reports"] / max(df["open_reports"].max(), 1)
    dens_norm = df["cool_points"] / max(df["cool_points"].max(), 1)
    df["deficit_index"] = (
        100 * (0.40 * df["heat_base"] + 0.25 * (1 - df["green_ratio"]) + 0.20 * rep_norm + 0.15 * (1 - dens_norm))
    ).round(1)
    return df


def recommend(row: pd.Series, reports: pd.DataFrame) -> str:
    open_rep = reports[(reports["district_id"] == row["id"]) & (reports["status"].isin(OPEN_STATUSES))] \
        if not reports.empty else reports
    no_shade = int((open_rep["type"].isin(["no_shade", "hot_surface"])).sum()) if not open_rep.empty else 0
    water = int((open_rep["type"] == "need_water").sum()) if not open_rep.empty else 0
    broken = int((open_rep["type"] == "broken_ac").sum()) if not open_rep.empty else 0
    idx = row["deficit_index"]
    base = 3 if idx >= 70 else 2 if idx >= 55 else 1 if idx >= 40 else 0
    parts = []
    shades = base + math.ceil(no_shade / 2)
    fountains = (1 if base >= 2 else 0) + water
    if shades:
        parts.append(f"навесы: {shades}")
    if fountains:
        parts.append(f"фонтанчики: {fountains}")
    if broken:
        parts.append(f"ремонт кондиционеров: {broken}")
    if idx >= 70:
        parts.append("новая остановка с кондиционером")
    return ", ".join(parts) if parts else "мониторинг"


def index_color(v: float) -> str:
    if v < 35:
        return "#F3DC7B"
    if v < 50:
        return "#F2B443"
    if v < 65:
        return "#EB8A2F"
    if v < 80:
        return "#DB5A2B"
    return "#B3342A"


def create_report(rtype: str, comment: str, lat: float, lon: float, source: str = "form") -> tuple[int, str]:
    districts = load_districts()
    d = nearest_district((lat, lon), districts)
    ts = now_aktau().isoformat()
    rid = db_execute(
        "INSERT INTO reports (type, comment, lat, lon, district_id, status, source, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (rtype, comment.strip(), lat, lon, int(d["id"]), "new", source, ts, ts),
    )
    db_execute(
        "INSERT INTO report_status_log (report_id, old_status, new_status, note, changed_at) VALUES (?,?,?,?,?)",
        (rid, None, "new", "Заявка создана", ts),
    )
    return rid, d["name"]


def change_status(report_id: int, new_status: str, note: str) -> None:
    row = db_query("SELECT status FROM reports WHERE id = ?", (report_id,))
    if row.empty:
        return
    old = row.iloc[0]["status"]
    ts = now_aktau().isoformat()
    db_execute("UPDATE reports SET status = ?, updated_at = ? WHERE id = ?", (new_status, ts, report_id))
    db_execute(
        "INSERT INTO report_status_log (report_id, old_status, new_status, note, changed_at) VALUES (?,?,?,?,?)",
        (report_id, old, new_status, note.strip() or None, ts),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Погода (Open-Meteo, без ключа)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def fetch_weather() -> dict | None:
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 43.65,
                "longitude": 51.17,
                "current": "temperature_2m,apparent_temperature,wind_speed_10m,relative_humidity_2m",
                "hourly": "apparent_temperature,uv_index",
                "forecast_hours": 12,
                "timezone": "Asia/Aqtau",
            },
            timeout=6,
        )
        r.raise_for_status()
        data = r.json()
        cur = data["current"]
        return {
            "temp": cur["temperature_2m"],
            "feels": cur["apparent_temperature"],
            "wind": cur["wind_speed_10m"],
            "humidity": cur["relative_humidity_2m"],
            "uv": max(data["hourly"]["uv_index"][:6] or [0]),
            "hourly_time": data["hourly"]["time"],
            "hourly_feels": data["hourly"]["apparent_temperature"],
            "source": "Open-Meteo, сейчас",
        }
    except Exception:
        return None


def simulated_weather() -> dict:
    hours = [(now_aktau() + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(12)]
    curve = [41, 42, 43, 43, 42, 40, 38, 35, 33, 31, 30, 29]
    return {"temp": 39.0, "feels": 41.0, "wind": 4.0, "humidity": 18, "uv": 9.5,
            "hourly_time": hours, "hourly_feels": curve, "source": "Сценарий «июль, +41 °C» (симуляция)"}


def heat_level(feels: float) -> str:
    if feels < 27:
        return "normal"
    if feels < 32:
        return "caution"
    if feels < 39:
        return "danger"
    return "extreme"


def heat_factor(feels: float) -> float:
    """Коэффициент текущей жары для тепловой нагрузки маршрута."""
    return max(0.35, min(1.3, (feels - 18) / 22))


# ──────────────────────────────────────────────────────────────────────────────
# CoolPath: маршруты и оценка тепловой нагрузки
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def osrm_foot(coords: tuple, alternatives: bool) -> list:
    """Пешие маршруты OSRM по графу OpenStreetMap. Пустой список, если сервис недоступен."""
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
    try:
        r = requests.get(
            f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{path}",
            params={"overview": "full", "geometries": "geojson", "alternatives": "true" if alternatives else "false"},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            return []
        return [
            {"pts": [(c[1], c[0]) for c in rt["geometry"]["coordinates"]], "distance": rt["distance"]}
            for rt in data["routes"]
        ]
    except Exception:
        return []


def straight_route(coords: tuple) -> dict:
    """Запасной вариант без сети: ломаная через точки, длина с поправкой 1.2 на уличную сеть."""
    pts = list(coords)
    return {"pts": pts, "distance": polyline_length(pts) * 1.2}


def evaluate_route(pts: list, distance: float, districts: pd.DataFrame, points: pd.DataFrame,
                   hfactor: float) -> dict:
    samples = resample(pts)
    pt_rows = list(points[["name", "type", "lat", "lon"]].itertuples(index=False))
    dist_rows = list(districts[["name", "lat", "lon", "heat_base"]].itertuples(index=False))
    values, shaded, stops = [], 0, {}
    worst = (-1.0, None, None)
    for s in samples:
        d = min(dist_rows, key=lambda r: haversine_m(s, (r.lat, r.lon)))
        relief = 0.0
        for p in pt_rows:
            if abs(p.lat - s[0]) > 0.004 or abs(p.lon - s[1]) > 0.005:
                continue
            dist_m = haversine_m(s, (p.lat, p.lon))
            radius, strength = RELIEF[p.type]
            if dist_m <= radius:
                relief = max(relief, strength)
            if dist_m <= 120:
                stops[p.name] = p.type
        v = d.heat_base * (1 - relief)
        values.append(v)
        if relief >= 0.3:
            shaded += 1
        if v > worst[0]:
            worst = (v, s, d.name)
    n = max(len(values), 1)
    duration = distance / 1000 / WALK_SPEED_KMH * 60
    exposure = min(100.0, sum(values) / n * hfactor * 100)
    return {
        "distance": distance,
        "duration": duration,
        "exposure": round(exposure, 1),
        "shade_index": round(100 * shaded / n, 1),
        "load": round(exposure * duration / 10, 1),
        "stops": stops,
        "worst_point": worst[1],
        "worst_district": worst[2],
    }


def build_cool_routes(a: tuple, b: tuple, districts: pd.DataFrame, points: pd.DataFrame, hfactor: float) -> dict:
    candidates = []
    direct = osrm_foot((a, b), True)
    source = "OSRM · OpenStreetMap (пешеходный граф)" if direct else "оценка по прямой (сервис маршрутов недоступен)"
    if direct:
        for i, r in enumerate(direct[:3]):
            candidates.append(("Кратчайший" if i == 0 else f"Альтернатива {i}", r))
    else:
        candidates.append(("Кратчайший", straight_route((a, b))))

    # Варианты с заходом в точку охлаждения по пути (крюк не более 35 %)
    base = haversine_m(a, b)
    vias = []
    for p in points.itertuples(index=False):
        if p.type == "water":
            continue
        pp = (p.lat, p.lon)
        if haversine_m(a, pp) < 150 or haversine_m(pp, b) < 150:
            continue
        ratio = (haversine_m(a, pp) + haversine_m(pp, b)) / max(base, 1)
        if ratio <= 1.35:
            vias.append((-RELIEF[p.type][1], ratio, p))
    vias.sort(key=lambda x: (x[0], x[1]))
    used_types = set()
    for _, _, p in vias:
        if p.type in used_types or len(used_types) >= 2:
            continue
        used_types.add(p.type)
        via = (p.lat, p.lon)
        r = osrm_foot((a, via, b), False)
        route = r[0] if r else straight_route((a, via, b))
        candidates.append((f"Через {LAYERS[p.type]['emoji']} {p.name}", route))

    results = []
    for label, r in candidates:
        ev = evaluate_route(r["pts"], r["distance"], districts, points, hfactor)
        dup = any(abs(x["distance"] - ev["distance"]) < 0.02 * ev["distance"] and abs(x["exposure"] - ev["exposure"]) < 1
                  for x in results)
        if not dup:
            results.append({"label": label, "pts": r["pts"], **ev})

    shortest = min(results, key=lambda x: x["distance"])
    allowed = [x for x in results if x["distance"] <= shortest["distance"] * MAX_DETOUR] or [shortest]
    best = min(allowed, key=lambda x: x["load"])
    for x in results:
        x["recommended"] = x is best
    return {"routes": results, "best": best, "shortest": shortest, "source": source}


# ──────────────────────────────────────────────────────────────────────────────
# Карты
# ──────────────────────────────────────────────────────────────────────────────
def base_map(center=AKTAU_CENTER, zoom=13) -> folium.Map:
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    # Тёплая приглушённая подложка в тон палитре приложения
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-tile-pane{filter:sepia(.28) saturate(.75) brightness(1.04) contrast(.95);}</style>"))
    return m


def emoji_icon(emoji: str, size: int = 22) -> folium.DivIcon:
    return folium.DivIcon(
        html=f'<div style="font-size:{size}px;line-height:{size}px;'
             f'filter:drop-shadow(0 0 2px #fff) drop-shadow(0 0 2px #fff)">{emoji}</div>',
        icon_size=(size + 4, size + 4),
        icon_anchor=((size + 4) // 2, (size + 4) // 2),
    )


def add_points(m: folium.Map, points: pd.DataFrame, types: list) -> None:
    for t in types:
        fg = folium.FeatureGroup(name=f"{LAYERS[t]['emoji']} {LAYERS[t]['label']}")
        for p in points[points["type"] == t].itertuples(index=False):
            badge = "проверено командой" if p.is_verified else "координаты уточняются"
            folium.Marker(
                (p.lat, p.lon),
                icon=emoji_icon(LAYERS[t]["emoji"]),
                tooltip=p.name,
                popup=folium.Popup(f"<b>{p.name}</b><br>{p.description}<br><i>{badge}</i>", max_width=260),
            ).add_to(fg)
        fg.add_to(m)


def add_districts(m: folium.Map, stats: pd.DataFrame) -> None:
    fg = folium.FeatureGroup(name="🔥 Зоны перегрева (индекс дефицита тени)")
    for r in stats.itertuples(index=False):
        c = index_color(r.deficit_index)
        folium.Circle(
            (r.lat, r.lon), radius=420, color=c, weight=1, fill=True, fill_color=c, fill_opacity=0.38,
            tooltip=f"{r.name}: индекс {r.deficit_index}",
            popup=folium.Popup(
                f"<b>{r.name}</b><br>Индекс дефицита тени: <b>{r.deficit_index}</b><br>"
                f"Зелень: {int(r.green_ratio * 100)} %<br>Точек охлаждения рядом: {r.cool_points}<br>"
                f"Открытых заявок: {r.open_reports}", max_width=240),
        ).add_to(fg)
    fg.add_to(m)


def add_reports(m: folium.Map, reports: pd.DataFrame, heat: bool, markers: bool) -> None:
    if reports.empty:
        return
    if heat:
        data = [[r.lat, r.lon, 1.0 if r.status in OPEN_STATUSES else 0.25] for r in reports.itertuples(index=False)]
        HeatMap(data, name="🌡 Тепловая карта обращений", radius=28, blur=22, min_opacity=0.35,
                gradient={0.3: "#F7D774", 0.6: "#EE8A2F", 1.0: "#B3342A"}).add_to(m)
    if markers:
        fg = folium.FeatureGroup(name="📣 Заявки жителей")
        for r in reports.itertuples(index=False):
            folium.CircleMarker(
                (r.lat, r.lon), radius=6, color="#fff", weight=1.5, fill=True,
                fill_color=STATUS_COLORS.get(r.status, "#999"), fill_opacity=0.95,
                tooltip=f"№{r.id} · {STATUSES.get(r.status, r.status)}",
                popup=folium.Popup(
                    f"<b>Заявка №{r.id}</b><br>{REPORT_TYPES.get(r.type, r.type)}<br>{r.district}<br>"
                    f"Статус: <b>{STATUSES.get(r.status, r.status)}</b><br><i>{r.comment or ''}</i>", max_width=260),
            ).add_to(fg)
        fg.add_to(m)


# ──────────────────────────────────────────────────────────────────────────────
# Оформление: нежно-жёлтая палитра
# ──────────────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700;800&display=swap');
:root{
  --cb-bg:#FFFBEA; --cb-sand:#FFF3C7; --cb-butter:#FBE7A1; --cb-sun:#F2C94C; --cb-sun-deep:#D9A521;
  --cb-ink:#43360F; --cb-muted:#85764A; --cb-line:#EFDFA2; --cb-sea:#23868A; --cb-sea-soft:#DDF1EE;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .stMarkdown, button, input, textarea{
  font-family:'Onest', 'Segoe UI', Roboto, Arial, sans-serif !important;
}
[data-testid="stAppViewContainer"]{ background:var(--cb-bg); color:var(--cb-ink); }
[data-testid="stHeader"]{ background:transparent; }
[data-testid="stSidebar"]{ background:var(--cb-sand); border-right:1px solid var(--cb-line); }
.block-container{ padding-top:1.6rem; max-width:1320px; }
h1, h2, h3, h4{ color:var(--cb-ink) !important; letter-spacing:-0.01em; }
.stMarkdown p, .stCaption, label{ color:var(--cb-ink); }

.cb-hero{
  display:grid; grid-template-columns:1.4fr 1fr; gap:24px; align-items:stretch;
  background:var(--cb-butter); border:1px solid var(--cb-line); border-radius:22px; padding:22px 26px; margin-bottom:14px;
}
.cb-hero h1{ font-size:2.4rem; font-weight:800; margin:0 0 6px 0; line-height:1.05; }
.cb-hero p{ margin:0; color:var(--cb-muted); font-size:1.02rem; max-width:62ch; }
.cb-temp{ background:#FFFDF4; border-radius:16px; padding:14px 18px; border-left:6px solid var(--lvl); }
.cb-temp .big{ font-size:2.6rem; font-weight:800; line-height:1; color:var(--cb-ink); }
.cb-temp .lvl{ display:inline-block; margin-left:10px; padding:3px 10px; border-radius:999px;
  background:var(--lvl); color:#fff; font-weight:700; font-size:.85rem; vertical-align:middle; }
.cb-temp .meta{ color:var(--cb-muted); font-size:.9rem; margin-top:6px; }
.cb-temp .advice{ margin-top:8px; font-weight:500; }

.cb-note{ background:var(--cb-sea-soft); border-radius:14px; padding:12px 16px; color:#1D5557; margin:6px 0 12px; }
.cb-route{ background:#FFFDF4; border:1px solid var(--cb-line); border-radius:14px; padding:12px 16px; margin-bottom:10px; }
.cb-route.best{ border:2px solid var(--cb-sea); background:#F4FBF9; }
.cb-route .t{ font-weight:700; }
.cb-route .m{ color:var(--cb-muted); font-size:.92rem; }
.cb-legend span{ display:inline-block; margin-right:14px; font-size:.88rem; color:var(--cb-muted); }
.cb-legend i{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }

[data-testid="stMetric"]{ background:#FFFDF4; border:1px solid var(--cb-line); border-radius:14px; padding:12px 16px; }
[data-testid="stMetricValue"]{ color:var(--cb-ink); font-weight:800; }

.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button{
  background:var(--cb-sun); color:var(--cb-ink); border:1px solid var(--cb-sun-deep); border-radius:12px; font-weight:700;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover{
  background:var(--cb-sun-deep); color:#fff; border-color:var(--cb-sun-deep);
}
.stButton > button:focus-visible, [data-testid="stFormSubmitButton"] > button:focus-visible{
  outline:3px solid var(--cb-sea); outline-offset:2px;
}
.stTabs [data-baseweb="tab-list"]{ gap:6px; border-bottom:2px solid var(--cb-line); }
.stTabs [data-baseweb="tab"]{ background:var(--cb-sand); border-radius:12px 12px 0 0; padding:8px 16px; font-weight:600; }
.stTabs [aria-selected="true"]{ background:var(--cb-sun) !important; color:var(--cb-ink) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--cb-sun-deep); }
[data-testid="stForm"]{ background:#FFFDF4; border:1px solid var(--cb-line); border-radius:16px; }
[data-testid="stDataFrame"]{ border:1px solid var(--cb-line); border-radius:12px; }
iframe{ border-radius:16px; }

@media (max-width: 800px){
  .cb-hero{ grid-template-columns:1fr; padding:18px; }
  .cb-hero h1{ font-size:1.9rem; }
}
</style>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Интерфейс
# ──────────────────────────────────────────────────────────────────────────────
def render_hero(weather: dict, lang: str) -> None:
    lvl = heat_level(weather["feels"])
    name, color, advice = HEAT_LEVELS[lvl]
    st.markdown(
        f"""
<div class="cb-hero">
  <div>
    <h1>Caspian Breeze</h1>
    <p>{T[lang]['subtitle']}</p>
  </div>
  <div class="cb-temp" style="--lvl:{color}">
    <span class="big">{weather['temp']:.0f}°</span><span class="lvl">{name}</span>
    <div class="meta">{T[lang]['feels']} {weather['feels']:.0f}° · UV {weather['uv']:.0f} ·
      ветер {weather['wind']:.0f} км/ч · влажность {weather['humidity']:.0f} %</div>
    <div class="advice">{advice}</div>
    <div class="meta">{weather['source']}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def tab_map(districts, points, reports, stats, layers_on: dict) -> None:
    col_map, col_side = st.columns([3, 1.15], gap="large")
    with col_map:
        m = base_map()
        if layers_on["districts"]:
            add_districts(m, stats)
        add_points(m, points, [t for t in LAYERS if layers_on[t]])
        add_reports(m, reports, heat=layers_on["heatmap"], markers=layers_on["reports"])
        folium.LayerControl(collapsed=True).add_to(m)
        st_folium(m, height=580, use_container_width=True, returned_objects=[], key="main_map")
        st.markdown(
            '<div class="cb-legend">'
            '<span><i style="background:#F3DC7B"></i>индекс &lt;35</span>'
            '<span><i style="background:#F2B443"></i>35–50</span>'
            '<span><i style="background:#EB8A2F"></i>50–65</span>'
            '<span><i style="background:#DB5A2B"></i>65–80</span>'
            '<span><i style="background:#B3342A"></i>80+</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with col_side:
        st.subheader("Ближайшая прохлада")
        place = st.selectbox("Я нахожусь в", districts["name"].tolist(), index=14, key="near_place")
        d = districts[districts["name"] == place].iloc[0]
        near = points.copy()
        near["dist"] = near.apply(lambda r: haversine_m((d["lat"], d["lon"]), (r["lat"], r["lon"])), axis=1)
        for r in near.nsmallest(5, "dist").itertuples(index=False):
            mins = r.dist * 1.2 / 1000 / WALK_SPEED_KMH * 60
            st.markdown(f"{LAYERS[r.type]['emoji']} **{r.name}**  \n{int(r.dist)} м · ~{mins:.0f} мин пешком")
        st.subheader("Самые жаркие микрорайоны")
        top = stats.nlargest(5, "deficit_index")[["name", "deficit_index", "open_reports"]]
        top.columns = ["Микрорайон", "Индекс", "Заявки"]
        st.dataframe(top, hide_index=True, width="stretch")


def tab_route(districts, points, hfactor: float) -> None:
    st.markdown(
        '<div class="cb-note">CoolPath строит несколько пеших вариантов и выбирает тот, где меньше открытого солнца: '
        "учитывается нагрев микрорайона, тень парков, бриз набережной и остановки с кондиционером по пути. "
        "Крюк — не больше 30 % к кратчайшему пути.</div>",
        unsafe_allow_html=True,
    )
    places = {f"📍 {r.name}": (r.lat, r.lon) for r in districts.itertuples(index=False)}
    places.update({f"{LAYERS[r.type]['emoji']} {r.name}": (r.lat, r.lon) for r in points.itertuples(index=False)})
    names = list(places)
    c1, c2, c3 = st.columns([2, 2, 1])
    src = c1.selectbox("Откуда", names, index=names.index("📍 27 мкр"), key="route_from")
    default_to = "🌊 Набережная Актау · 1 мкр"
    dst = c2.selectbox("Куда", names, index=names.index(default_to), key="route_to")
    c3.write("")
    c3.write("")
    if c3.button("Построить CoolPath", key="build_route", width="stretch"):
        if src == dst:
            st.warning("Выберите разные точки старта и финиша.")
        else:
            with st.spinner("Сравниваем варианты маршрута…"):
                st.session_state["route_result"] = build_cool_routes(places[src], places[dst], districts, points, hfactor)
                st.session_state["route_names"] = (src, dst)
                st.session_state.pop("route_report_id", None)

    res = st.session_state.get("route_result")
    if not res:
        st.info("Выберите точки и нажмите «Построить CoolPath». Для демо уже выбран путь из жаркого 27 мкр к набережной.")
        return

    best, shortest = res["best"], res["shortest"]
    col_map, col_list = st.columns([3, 1.3], gap="large")
    with col_map:
        m = base_map(zoom=14)
        for r in sorted(res["routes"], key=lambda x: x["recommended"]):
            folium.PolyLine(
                r["pts"], color="#23868A" if r["recommended"] else "#D9A521",
                weight=7 if r["recommended"] else 4, opacity=0.95 if r["recommended"] else 0.6,
                dash_array=None if r["recommended"] else "6 8",
                tooltip=f"{r['label']}: индекс тени {r['shade_index']} %, нагрузка {r['load']}",
            ).add_to(m)
        start, end = best["pts"][0], best["pts"][-1]
        folium.Marker(start, tooltip="Старт", icon=folium.Icon(color="orange", icon="play")).add_to(m)
        folium.Marker(end, tooltip="Финиш", icon=folium.Icon(color="cadetblue", icon="flag")).add_to(m)
        for name, t in best["stops"].items():
            row = points[points["name"] == name].iloc[0]
            folium.Marker((row["lat"], row["lon"]), icon=emoji_icon(LAYERS[t]["emoji"], 20),
                          tooltip=f"Точка отдыха: {name}").add_to(m)
        if best["worst_point"]:
            folium.CircleMarker(best["worst_point"], radius=13, color="#B3342A", weight=3, fill=True,
                                fill_opacity=0.25, tooltip="Самый открытый участок маршрута").add_to(m)
        m.fit_bounds([[min(p[0] for p in best["pts"]), min(p[1] for p in best["pts"])],
                      [max(p[0] for p in best["pts"]), max(p[1] for p in best["pts"])]])
        st_folium(m, height=520, use_container_width=True, returned_objects=[], key="route_map")
        st.caption(f"Источник геометрии: {res['source']}. Индекс тени — доля пути в зоне тени, бриза или укрытия.")
    with col_list:
        if best is not shortest and shortest["load"] > 0:
            gain = (shortest["load"] - best["load"]) / shortest["load"] * 100
            extra = best["duration"] - shortest["duration"]
            st.success(f"На {gain:.0f} % меньше тепловой нагрузки, чем кратчайший путь, "
                       f"ценой +{max(extra, 0):.0f} мин.")
        else:
            st.success("Кратчайший путь здесь и самый прохладный.")
        for r in sorted(res["routes"], key=lambda x: x["load"]):
            cls = "cb-route best" if r["recommended"] else "cb-route"
            tag = "✅ Рекомендуем · " if r["recommended"] else ""
            st.markdown(
                f'<div class="{cls}"><div class="t">{tag}{r["label"]}</div>'
                f'<div class="m">{r["distance"] / 1000:.2f} км · {r["duration"]:.0f} мин · '
                f'индекс тени {r["shade_index"]:.0f} % · нагрузка {r["load"]}</div></div>',
                unsafe_allow_html=True,
            )
        if best["stops"]:
            st.markdown("**Где передохнуть по пути:** " +
                        ", ".join(f"{LAYERS[t]['emoji']} {n}" for n, t in best["stops"].items()))

        st.markdown("---")
        st.markdown(f"**Самый открытый участок** — {best['worst_district']}. Нужен навес или деревья?")
        if st.session_state.get("route_report_id"):
            st.info(f"Заявка №{st.session_state['route_report_id']} уже отправлена в акимат.")
        elif st.button("📣 Сообщить: здесь нет тени", key="route_report", width="stretch"):
            lat, lon = best["worst_point"]
            a, b = st.session_state.get("route_names", ("", ""))
            rid, dname = create_report(
                "no_shade", f"CoolPath {a} → {b}: открытый участок без тени", lat, lon, source="coolpath"
            )
            st.session_state["route_report_id"] = rid
            st.toast(f"Заявка №{rid} принята · {dname}", icon="📣")
            st.rerun()


def tab_report(districts, reports) -> None:
    col_form, col_status = st.columns([1.6, 1], gap="large")
    with col_form:
        st.subheader("Новая заявка")
        st.caption("Нажмите на карту, чтобы указать место. Без клика заявка привяжется к центру выбранного микрорайона.")
        m = base_map(zoom=13)
        picked = st.session_state.get("report_point")
        if picked:
            folium.Marker(picked, tooltip="Место проблемы", icon=folium.Icon(color="red", icon="exclamation-sign")).add_to(m)
        out = st_folium(m, height=360, use_container_width=True, returned_objects=["last_clicked"], key="report_map")
        if out and out.get("last_clicked"):
            new_pt = (out["last_clicked"]["lat"], out["last_clicked"]["lng"])
            if new_pt != picked:
                st.session_state["report_point"] = new_pt
                st.rerun()

        with st.form("report_form", clear_on_submit=True):
            rtype = st.selectbox("Что не так", list(REPORT_TYPES), format_func=REPORT_TYPES.get)
            fallback = st.selectbox("Микрорайон (если не отмечали на карте)", districts["name"].tolist(), index=14)
            comment = st.text_area("Комментарий", placeholder="Например: у школы №12 нет ни одного навеса, дети ждут на солнце",
                                   max_chars=500)
            sent = st.form_submit_button("Отправить заявку", width="stretch")
        if sent:
            if st.session_state.get("report_point"):
                lat, lon = st.session_state["report_point"]
            else:
                d = districts[districts["name"] == fallback].iloc[0]
                lat, lon = float(d["lat"]), float(d["lon"])
            rid, dname = create_report(rtype, comment, lat, lon)
            st.session_state.pop("report_point", None)
            st.session_state["last_report_id"] = rid
            st.success(f"Заявка №{rid} принята. Микрорайон: {dname}. Сохраните номер, чтобы проверить статус.")

    with col_status:
        st.subheader("Статус моей заявки")
        default_id = int(st.session_state.get("last_report_id") or (reports["id"].max() if not reports.empty else 1))
        rid = st.number_input("Номер заявки", min_value=1, step=1, value=default_id, key="status_lookup")
        row = db_query(
            "SELECT r.*, d.name AS district FROM reports r LEFT JOIN districts d ON d.id = r.district_id WHERE r.id = ?",
            (int(rid),),
        )
        if row.empty:
            st.info("Заявка с таким номером не найдена. Проверьте номер из уведомления.")
        else:
            r = row.iloc[0]
            color = STATUS_COLORS.get(r["status"], "#999")
            st.markdown(
                f"**{REPORT_TYPES.get(r['type'], r['type'])}** · {r['district']}  \n"
                f"<span style='background:{color};color:#fff;padding:3px 10px;border-radius:999px;font-weight:700'>"
                f"{STATUSES.get(r['status'], r['status'])}</span>",
                unsafe_allow_html=True,
            )
            if r["comment"]:
                st.caption(r["comment"])
            log = db_query(
                "SELECT changed_at, new_status, note FROM report_status_log WHERE report_id = ? ORDER BY id",
                (int(rid),),
            )
            for e in log.itertuples(index=False):
                when = pd.to_datetime(e.changed_at).strftime("%d.%m %H:%M")
                st.markdown(f"`{when}` {STATUSES.get(e.new_status, e.new_status)}" + (f" — {e.note}" if e.note else ""))


def admin_live_panel() -> None:
    """Обновляется сам каждые 20 секунд: новые заявки видны диспетчеру без перезагрузки."""
    districts, points, reports = load_districts(), load_points(), load_reports()
    stats = district_stats(districts, points, reports)
    prev = district_stats(districts, points, reports, exclude_after=now_aktau() - timedelta(hours=24))
    stats["delta_24h"] = (stats["deficit_index"] - prev["deficit_index"]).round(1)

    open_cnt = int(reports["status"].isin(OPEN_STATUSES).sum()) if not reports.empty else 0
    last24 = int((reports["created_at"] >= pd.Timestamp(now_aktau() - timedelta(hours=24))).sum()) if not reports.empty else 0
    worst = stats.sort_values("deficit_index", ascending=False).iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Открытые заявки", open_cnt)
    k2.metric("Новые за 24 ч", last24)
    k3.metric("Средний индекс дефицита", f"{stats['deficit_index'].mean():.1f}")
    k4.metric(f"Хуже всего: {worst['name']}", f"{worst['deficit_index']}", delta=f"{worst['delta_24h']:+.1f} за 24 ч",
              delta_color="inverse")

    st.markdown("**Лента обращений**")
    feed = reports.head(8).copy()
    if feed.empty:
        st.info("Обращений пока нет.")
    else:
        feed["Когда"] = feed["created_at"].dt.strftime("%d.%m %H:%M")
        feed["Тип"] = feed["type"].map(REPORT_TYPES)
        feed["Статус"] = feed["status"].map(STATUSES)
        feed = feed.rename(columns={"id": "№", "district": "Микрорайон", "comment": "Комментарий"})
        st.dataframe(feed[["№", "Когда", "Микрорайон", "Тип", "Статус", "Комментарий"]],
                     hide_index=True, width="stretch")
    st.caption(f"Обновлено {now_aktau().strftime('%H:%M:%S')} · автообновление каждые 20 с")


def tab_admin(districts, points, reports, stats) -> None:
    token = st.text_input("Токен диспетчера", type="password", key="admin_token",
                          help="Для демо на хакатоне: aktau2026 (меняется переменной CB_ADMIN_TOKEN)")
    if token != ADMIN_TOKEN:
        st.info("Введите токен диспетчера, чтобы открыть панель акимата.")
        return

    fragment = getattr(st, "fragment", None)
    (fragment(run_every="20s")(admin_live_panel) if fragment else admin_live_panel)()

    st.markdown("---")
    col_map, col_rank = st.columns([1.5, 1.2], gap="large")
    with col_map:
        st.subheader("Где жалуются на жару")
        m = base_map()
        add_districts(m, stats)
        add_reports(m, reports, heat=True, markers=False)
        folium.LayerControl(collapsed=True).add_to(m)
        st_folium(m, height=440, use_container_width=True, returned_objects=[], key="admin_map")
    with col_rank:
        st.subheader("Рейтинг микрорайонов")
        rank = stats.sort_values("deficit_index", ascending=False).copy()
        rank["Что установить"] = rank.apply(lambda r: recommend(r, reports), axis=1)
        rank = rank.rename(columns={"name": "Микрорайон", "deficit_index": "Индекс",
                                    "open_reports": "Заявки", "cool_points": "Точки охл."})
        st.dataframe(rank[["Микрорайон", "Индекс", "Заявки", "Точки охл.", "Что установить"]],
                     hide_index=True, width="stretch", height=440)

    st.subheader("Обработка заявок")
    open_rep = reports[reports["status"].isin(OPEN_STATUSES)] if not reports.empty else reports
    if open_rep.empty:
        st.info("Открытых заявок нет.")
    else:
        with st.form("status_form"):
            c1, c2, c3 = st.columns([2.2, 1.4, 2])
            options = open_rep["id"].tolist()
            labels = {r.id: f"№{r.id} · {REPORT_TYPES.get(r.type, r.type)} · {r.district} · {STATUSES[r.status]}"
                      for r in open_rep.itertuples(index=False)}
            rid = c1.selectbox("Заявка", options, format_func=labels.get)
            new_status = c2.selectbox("Новый статус", list(STATUSES), index=2, format_func=STATUSES.get)
            note = c3.text_input("Комментарий для жителя", placeholder="Навес включён в план благоустройства")
            if st.form_submit_button("Сохранить статус"):
                change_status(int(rid), new_status, note)
                st.toast(f"Статус заявки №{rid}: {STATUSES[new_status]}", icon="🏛")
                st.rerun()

    st.subheader("Динамика")
    ch1, ch2 = st.columns(2)
    if not reports.empty:
        daily = reports.set_index("created_at").resample("D").size().rename("Заявки")
        daily.index = daily.index.strftime("%d.%m")
        ch1.caption("Заявки по дням")
        ch1.bar_chart(daily, color="#D9A521")
        by_type = reports["type"].map(REPORT_TYPES).value_counts().rename("Заявки")
        ch2.caption("По типам проблем")
        ch2.bar_chart(by_type, color="#23868A", horizontal=True)

    st.subheader("Все заявки")
    f1, f2 = st.columns(2)
    sel_status = f1.multiselect("Статус", list(STATUSES), default=list(OPEN_STATUSES), format_func=STATUSES.get)
    sel_district = f2.multiselect("Микрорайон", districts["name"].tolist())
    table = reports.copy()
    if not table.empty:
        if sel_status:
            table = table[table["status"].isin(sel_status)]
        if sel_district:
            table = table[table["district"].isin(sel_district)]
        table["Тип"] = table["type"].map(REPORT_TYPES)
        table["Статус"] = table["status"].map(STATUSES)
        table["Создана"] = table["created_at"].dt.strftime("%d.%m.%Y %H:%M")
        table = table.rename(columns={"id": "№", "district": "Микрорайон", "comment": "Комментарий",
                                      "lat": "Широта", "lon": "Долгота", "source": "Источник"})
        cols = ["№", "Создана", "Микрорайон", "Тип", "Статус", "Комментарий", "Источник", "Широта", "Долгота"]
        st.dataframe(table[cols], hide_index=True, width="stretch")
        st.download_button("Скачать CSV для отдела благоустройства",
                           table[cols].to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"caspian_breeze_reports_{now_aktau():%Y%m%d}.csv", mime="text/csv")

    with st.expander("Демо-режим"):
        st.caption("Возвращает базу к исходному состоянию: удаляет новые заявки и историю статусов.")
        if st.button("Сбросить демо-данные", key="reset_demo"):
            init_db(force_reset=True)
            st.session_state.clear()
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(page_title="Caspian Breeze · Актау", page_icon="🌊", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    bootstrap_db()

    with st.sidebar:
        lang = st.radio("Язык / Тіл", ["ru", "kk"], format_func={"ru": "Русский", "kk": "Қазақша"}.get, horizontal=True)
        st.markdown("### Слои карты")
        layers_on = {t: st.checkbox(f"{v['emoji']} {v['label']}", value=True, key=f"layer_{t}") for t, v in LAYERS.items()}
        layers_on["districts"] = st.checkbox("🔥 Зоны перегрева", value=True, key="layer_districts")
        layers_on["heatmap"] = st.checkbox("🌡 Тепловая карта обращений", value=False, key="layer_heat")
        layers_on["reports"] = st.checkbox("📣 Заявки жителей", value=True, key="layer_reports")
        st.markdown("### Погода")
        live = fetch_weather()
        scenario = st.toggle("Сценарий «июль, +41 °C»", value=live is None or live["feels"] < 32,
                             help="В конце сентября в Актау прохладнее. Сценарий показывает работу платформы в пик жары.")
        weather = simulated_weather() if scenario or live is None else live
        if live is None:
            st.caption("Open-Meteo сейчас недоступен — используется сценарий жары.")
        st.markdown("---")
        st.caption("Caspian Breeze · MVP для хакатона Smart City Aktau · данные хранятся в SQLite на сервере")

    render_hero(weather, lang)
    hfactor = heat_factor(weather["feels"])

    districts, points, reports = load_districts(), load_points(), load_reports()
    stats = district_stats(districts, points, reports)

    t1, t2, t3, t4 = st.tabs([T[lang]["tab_map"], T[lang]["tab_route"], T[lang]["tab_report"], T[lang]["tab_admin"]])
    with t1:
        tab_map(districts, points, reports, stats, layers_on)
    with t2:
        tab_route(districts, points, hfactor)
    with t3:
        tab_report(districts, reports)
    with t4:
        tab_admin(districts, points, reports, stats)


if __name__ == "__main__":
    main()
