"""Pydantic-схемы API. Пространственные ответы — GeoJSON (Feature / FeatureCollection)."""
from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

# Допустимая область для новых заявок: г. Актау с пригородами
AKTAU_BOUNDS = {"lat_min": 43.55, "lat_max": 43.80, "lon_min": 51.05, "lon_max": 51.40}

CoolingType = Literal["mall", "ac_bus_stop", "park", "embankment", "fountain", "pharmacy", "library"]
ReportType = Literal["no_shade", "need_fountain", "broken_ac", "other"]
ReportStatus = Literal["new", "in_review", "planned", "done", "rejected"]
HeatLevel = Literal["normal", "caution", "danger", "extreme"]

P = TypeVar("P", bound=BaseModel)


# ── GeoJSON ──────────────────────────────────────────────────────────────────
class Feature(BaseModel, Generic[P]):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: dict[str, Any]
    properties: P


class FeatureCollection(BaseModel, Generic[P]):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature[P]]


def point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


# ── Погода ───────────────────────────────────────────────────────────────────
class HourlyWeather(BaseModel):
    time: str
    temperature: float
    feels_like: float
    uv_index: float


class Weather(BaseModel):
    temperature: float
    feels_like: float
    uv_index: float
    wind_speed: float = Field(description="км/ч")
    humidity: float = Field(description="%")
    heat_level: HeatLevel
    advice: str
    hourly: list[HourlyWeather]
    source: Literal["open-meteo", "simulation"]
    fetched_at: datetime
    cached: bool = False
    stale: bool = False


# ── Микрорайоны ──────────────────────────────────────────────────────────────
class IndexComponents(BaseModel):
    heat: float = Field(description="вклад нагрева, баллы")
    no_green: float = Field(description="вклад нехватки зелени, баллы")
    reports: float = Field(description="вклад открытых заявок, баллы")
    no_cooling: float = Field(description="вклад нехватки точек охлаждения, баллы")


class DistrictProps(BaseModel):
    name: str
    population: int | None
    green_ratio: float
    heat_index_base: float
    area_km2: float
    open_reports: int
    cooling_points: int
    cooling_density_km2: float
    shade_deficit_index: float
    index_components: IndexComponents


# ── Точки охлаждения ─────────────────────────────────────────────────────────
class CoolingPointProps(BaseModel):
    name: str
    type: CoolingType
    hours: str | None
    is_verified: bool
    district_id: int | None
    district_name: str | None
    distance_m: float | None = None


# ── Заявки ───────────────────────────────────────────────────────────────────
class ReportCreate(BaseModel):
    type: ReportType
    comment: str | None = Field(default=None, max_length=500)
    lat: float = Field(ge=AKTAU_BOUNDS["lat_min"], le=AKTAU_BOUNDS["lat_max"])
    lon: float = Field(ge=AKTAU_BOUNDS["lon_min"], le=AKTAU_BOUNDS["lon_max"])
    source: Literal["form", "coolpath"] = "form"


class StatusChange(BaseModel):
    status: ReportStatus
    note: str | None = Field(default=None, max_length=500)


class StatusLogEntry(BaseModel):
    old_status: ReportStatus | None
    new_status: ReportStatus
    note: str | None
    changed_at: datetime


class ReportProps(BaseModel):
    type: ReportType
    comment: str | None
    status: ReportStatus
    source: Literal["seed", "form", "coolpath"]
    district_id: int | None
    district_name: str | None
    created_at: datetime
    updated_at: datetime
    photo_url: str | None
    history: list[StatusLogEntry] | None = None


# ── CoolPath ─────────────────────────────────────────────────────────────────
LatLon = tuple[float, float]


class CoolRouteRequest(BaseModel):
    from_: Annotated[LatLon, Field(alias="from", description="[lat, lon] старта")]
    to: LatLon = Field(description="[lat, lon] финиша")
    scenario: Literal["heatwave"] | None = Field(default=None, description="heatwave — считать при +41 °C")

    model_config = {"populate_by_name": True}


class RestStop(BaseModel):
    id: int
    name: str
    type: CoolingType
    lat: float
    lon: float
    at_m: float = Field(description="на каком метре маршрута")


class HotSpot(BaseModel):
    lat: float
    lon: float
    district_name: str | None


class RouteOption(BaseModel):
    id: int
    label: str
    kind: Literal["shortest", "alternative", "via_cooling"]
    source: Literal["osrm", "straight"]
    geometry: dict[str, Any]
    distance_m: float
    duration_min: float
    heat_exposure: float = Field(description="0..100, средняя тепловая нагрузка на метр пути")
    shade_share_pct: float = Field(description="доля пути у тени, бриза или укрытия, %")
    heat_load: float = Field(description="«доза жары» = exposure × минуты / 10")
    rest_stops: list[RestStop]
    hottest_point: HotSpot | None
    recommended: bool


class RouteComparison(BaseModel):
    heat_less_pct: float
    extra_min: float
    text: str


class CoolRouteResponse(BaseModel):
    routes: list[RouteOption]
    recommended_id: int
    comparison: RouteComparison
    heat_factor: float
    feels_like: float | None
    weather_source: str


# ── Панель акимата ───────────────────────────────────────────────────────────
class Recommendation(BaseModel):
    shades: int
    fountains: int
    ac_repairs: int
    priority: Literal["high", "medium", "low"]
    text: str


class DistrictRating(BaseModel):
    id: int
    name: str
    shade_deficit_index: float
    index_components: IndexComponents
    open_reports: int
    open_by_type: dict[str, int]
    cooling_points: int
    cooling_density_km2: float
    green_ratio: float
    recommendation: Recommendation


class TopDistrict(BaseModel):
    id: int
    name: str
    shade_deficit_index: float
    open_reports: int


class Kpi(BaseModel):
    open_reports: int
    avg_deficit_index: float
    reports_7d: int
    reports_prev_7d: int
    top_districts: list[TopDistrict]


class DailyCount(BaseModel):
    date: str
    count: int


class TypeCount(BaseModel):
    type: ReportType
    count: int


class AdminSummary(BaseModel):
    kpi: Kpi
    districts: list[DistrictRating]
    daily: list[DailyCount]
    by_type: list[TypeCount]
    generated_at: datetime
