"""
Погода Актау из Open-Meteo (бесплатно, без ключа) с кешем в памяти на 10 минут.

Кеш нужен, чтобы при сотне открытых карт не делать сотню запросов к Open-Meteo:
в течение 10 минут все получают один и тот же ответ. Если Open-Meteo недоступен,
отдаём последний удачный ответ с пометкой stale=true; если его нет — ошибка 503.
Сценарий «heatwave» — типичный июльский день (+41 °C) для демонстрации в межсезонье;
он всегда помечен source="simulation".
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.schemas import HourlyWeather, Weather

AKTAU_LAT, AKTAU_LON = 43.65, 51.17
AKTAU_TZ = timezone(timedelta(hours=5))
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 600

_cache: dict = {"data": None, "ts": 0.0}
_lock = threading.Lock()


class WeatherUnavailable(Exception):
    pass


def heat_level(feels_like: float) -> str:
    """Пороги по ощущаемой температуре (близки к шкалам теплового стресса ВОЗ/NOAA)."""
    if feels_like < 27:
        return "normal"
    if feels_like < 32:
        return "caution"
    if feels_like < 39:
        return "danger"
    return "extreme"


ADVICE = {
    "normal": "Погода комфортная, ограничений нет.",
    "caution": "Пейте воду каждые 30–40 минут и выбирайте теневые улицы.",
    "danger": "С 12:00 до 17:00 избегайте открытых участков, стройте маршрут через точки охлаждения.",
    "extreme": "Опасная жара: пожилым и детям оставаться в прохладе, маршруты только через точки охлаждения.",
}


def _fetch_open_meteo() -> dict:
    params = {
        "latitude": AKTAU_LAT,
        "longitude": AKTAU_LON,
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,relative_humidity_2m",
        "hourly": "temperature_2m,apparent_temperature,uv_index",
        "forecast_hours": 12,
        "timezone": "Asia/Aqtau",
    }
    resp = httpx.get(OPEN_METEO_URL, params=params, timeout=6.0)
    resp.raise_for_status()
    return resp.json()


def _parse(data: dict) -> Weather:
    cur, hourly = data["current"], data["hourly"]
    hours = [
        HourlyWeather(time=t, temperature=tt, feels_like=ff, uv_index=uv or 0)
        for t, tt, ff, uv in zip(hourly["time"], hourly["temperature_2m"],
                                 hourly["apparent_temperature"], hourly["uv_index"])
    ][:12]
    feels = cur["apparent_temperature"]
    level = heat_level(feels)
    return Weather(
        temperature=cur["temperature_2m"], feels_like=feels,
        uv_index=hours[0].uv_index if hours else 0, wind_speed=cur["wind_speed_10m"],
        humidity=cur["relative_humidity_2m"], heat_level=level, advice=ADVICE[level],
        hourly=hours, source="open-meteo", fetched_at=datetime.now(AKTAU_TZ).replace(microsecond=0),
    )


def simulated_heatwave() -> Weather:
    # Типичный июльский день с 11:00 (пик жары — 13–15 ч), независимо от текущего часа
    now = datetime.now(AKTAU_TZ).replace(hour=11, minute=0, second=0, microsecond=0)
    curve = [41, 42, 43, 43, 42, 40, 38, 35, 33, 31, 30, 29]
    uv = [9, 10, 10, 9, 8, 6, 4, 2, 1, 0, 0, 0]
    hours = [HourlyWeather(time=(now + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"),
                           temperature=c - 2, feels_like=c, uv_index=u) for i, (c, u) in enumerate(zip(curve, uv))]
    return Weather(temperature=39, feels_like=41, uv_index=9, wind_speed=4, humidity=18,
                   heat_level="extreme", advice=ADVICE["extreme"], hourly=hours,
                   source="simulation", fetched_at=now)


def get_weather(scenario: str | None = None) -> Weather:
    if scenario == "heatwave":
        return simulated_heatwave()
    with _lock:
        cached = _cache["data"]
        if cached and time.monotonic() - _cache["ts"] < CACHE_TTL_S:
            return cached.model_copy(update={"cached": True})
    try:
        weather = _parse(_fetch_open_meteo())
    except Exception as exc:  # сеть, таймаут, формат ответа
        if cached:
            return cached.model_copy(update={"cached": True, "stale": True})
        raise WeatherUnavailable(str(exc)) from exc
    with _lock:
        _cache["data"], _cache["ts"] = weather, time.monotonic()
    return weather


def clear_cache() -> None:
    with _lock:
        _cache["data"], _cache["ts"] = None, 0.0
