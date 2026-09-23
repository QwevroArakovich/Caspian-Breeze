from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import COOLING_TYPES, CoolingPoint, District
from app.schemas import CoolingPointProps, Feature, FeatureCollection, point

router = APIRouter(prefix="/api/cooling-points", tags=["cooling-points"])


def _parse_types(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    types = [t.strip() for t in raw.split(",") if t.strip()]
    bad = [t for t in types if t not in COOLING_TYPES]
    if bad:
        raise HTTPException(422, detail=f"Неизвестный тип: {', '.join(bad)}. Допустимо: {', '.join(COOLING_TYPES)}")
    return types


def _base_select():
    return (
        select(CoolingPoint.id, CoolingPoint.name, CoolingPoint.type, CoolingPoint.hours, CoolingPoint.is_verified,
               CoolingPoint.district_id, District.name.label("district_name"),
               func.ST_X(CoolingPoint.geom).label("lon"), func.ST_Y(CoolingPoint.geom).label("lat"))
        .outerjoin(District, District.id == CoolingPoint.district_id)
    )


def _to_feature(r, distance: float | None = None) -> Feature[CoolingPointProps]:
    return Feature[CoolingPointProps](
        id=r.id, geometry=point(r.lon, r.lat),
        properties=CoolingPointProps(name=r.name, type=r.type, hours=r.hours, is_verified=r.is_verified,
                                     district_id=r.district_id, district_name=r.district_name,
                                     distance_m=None if distance is None else round(distance, 1)),
    )


@router.get("", response_model=FeatureCollection[CoolingPointProps])
def list_points(
    db: Session = Depends(get_db),
    type: Annotated[str | None, Query(description="тип или список через запятую: park,fountain")] = None,
    bbox: Annotated[str | None, Query(description="minLon,minLat,maxLon,maxLat")] = None,
):
    """Точки охлаждения с фильтром по типу и видимой области карты."""
    stmt = _base_select().order_by(CoolingPoint.type, CoolingPoint.name)
    types = _parse_types(type)
    if types:
        stmt = stmt.where(CoolingPoint.type.in_(types))
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(422, detail="bbox должен быть в формате minLon,minLat,maxLon,maxLat")
        envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = stmt.where(CoolingPoint.geom.op("&&")(envelope))
    return FeatureCollection[CoolingPointProps](features=[_to_feature(r) for r in db.execute(stmt)])


@router.get("/nearest", response_model=FeatureCollection[CoolingPointProps])
def nearest(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    type: Annotated[str | None, Query(description="тип или список через запятую")] = None,
    db: Session = Depends(get_db),
):
    """Ближайшие точки охлаждения. Сортировка — KNN-индекс PostGIS (<->), расстояние — ST_Distance в метрах."""
    here = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    distance = func.ST_Distance(func.Geography(CoolingPoint.geom), func.Geography(here)).label("distance_m")
    stmt = _base_select().add_columns(distance).order_by(CoolingPoint.geom.op("<->")(here)).limit(limit * 3)
    types = _parse_types(type)
    if types:
        stmt = stmt.where(CoolingPoint.type.in_(types))
    # KNN по планарным градусам почти совпадает с геодезическим порядком; берём с запасом и досортировываем по метрам
    rows = sorted(db.execute(stmt), key=lambda r: r.distance_m)[:limit]
    return FeatureCollection[CoolingPointProps](features=[_to_feature(r, r.distance_m) for r in rows])
