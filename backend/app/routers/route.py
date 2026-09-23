from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AKTAU_BOUNDS, CoolRouteRequest, CoolRouteResponse, RouteOption
from app.services.routing import cool_routes
from app.services.weather import WeatherUnavailable, get_weather

router = APIRouter(prefix="/api/route", tags=["coolpath"])


def _in_aktau(lat: float, lon: float) -> bool:
    b = AKTAU_BOUNDS
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


@router.post("/cool", response_model=CoolRouteResponse)
def cool(payload: CoolRouteRequest, db: Session = Depends(get_db)):
    """
    CoolPath: несколько пеших вариантов (OSRM + заход в точку охлаждения) с оценкой тепловой нагрузки.
    recommended — минимальная тепловая нагрузка (heat_exposure) среди вариантов не длиннее кратчайшего более чем на 30 %.
    """
    start, end = tuple(payload.from_), tuple(payload.to)
    if not (_in_aktau(*start) and _in_aktau(*end)):
        raise HTTPException(422, detail="Старт и финиш должны быть в Актау")
    dist = db.execute(text("SELECT ST_Distance(ST_MakePoint(:a, :b)::geography, ST_MakePoint(:c, :d)::geography)"),
                      {"a": start[1], "b": start[0], "c": end[1], "d": end[0]}).scalar()
    if dist < 50:
        raise HTTPException(422, detail="Старт и финиш слишком близко — меньше 50 м")
    if dist > 15_000:
        raise HTTPException(422, detail="Слишком далеко для пешего маршрута — больше 15 км")

    try:
        weather = get_weather(payload.scenario)
        feels, weather_source = weather.feels_like, weather.source
    except WeatherUnavailable:
        feels, weather_source = None, "unavailable"

    result = cool_routes(start, end, feels, db)
    routes = [
        RouteOption(
            id=i, label=e.raw.label, kind=e.raw.kind, source=e.raw.source,
            geometry={"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in e.raw.coords]},
            distance_m=round(e.raw.distance_m), duration_min=e.duration_min, heat_exposure=e.heat_exposure,
            shade_share_pct=e.shade_share_pct, heat_load=e.heat_load, rest_stops=e.rest_stops,
            hottest_point=e.hottest, recommended=e is result["best"],
        )
        for i, e in enumerate(result["evaluated"])
    ]
    return CoolRouteResponse(
        routes=routes, recommended_id=next(r.id for r in routes if r.recommended),
        comparison=result["comparison"], heat_factor=round(result["factor"], 2),
        feels_like=feels, weather_source=weather_source,
    )
