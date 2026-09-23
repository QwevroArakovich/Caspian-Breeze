from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas import Weather
from app.services.weather import WeatherUnavailable, get_weather

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather", response_model=Weather)
def weather(scenario: Literal["heatwave"] | None = Query(
        default=None, description="heatwave — симуляция июльской жары (+41 °C) для демонстрации")):
    """Текущая погода и прогноз на 12 ч для Актау (Open-Meteo, кеш 10 минут)."""
    try:
        return get_weather(scenario)
    except WeatherUnavailable:
        raise HTTPException(503, detail="Open-Meteo недоступен. Для демо используйте ?scenario=heatwave")
