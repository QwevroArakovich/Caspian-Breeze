from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DistrictProps, Feature, FeatureCollection
from app.services.districts import district_stats

router = APIRouter(prefix="/api", tags=["districts"])


@router.get("/districts", response_model=FeatureCollection[DistrictProps])
def districts(db: Session = Depends(get_db)):
    """Микрорайоны с полигонами и рассчитанным индексом дефицита тени (0..100)."""
    features = [
        Feature[DistrictProps](
            id=r["id"], geometry=r["geometry"],
            properties=DistrictProps(
                name=r["name"], population=r["population"], green_ratio=r["green_ratio"],
                heat_index_base=r["heat_index_base"], area_km2=round(r["area_km2"], 3),
                open_reports=r["open_reports"], cooling_points=r["cooling_points"],
                cooling_density_km2=round(r["cooling_density_km2"], 2),
                shade_deficit_index=r["shade_deficit_index"], index_components=r["index_components"],
            ),
        )
        for r in district_stats(db)
    ]
    return FeatureCollection[DistrictProps](features=features)
