"""Caspian Breeze API — точка входа FastAPI."""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.routers import admin, cooling_points, districts, reports, route, weather

settings = get_settings()

if settings.app_env == "production" and settings.admin_token in {"change-me", "", "aktau2026"}:
    # Защита от деплоя с токеном из примера: панель акимата была бы открыта всем
    raise RuntimeError("ADMIN_TOKEN не задан: укажите свой длинный токен в переменных окружения сервиса")

app = FastAPI(title="Caspian Breeze API", version="0.8.0",
              description="Платформа теплового комфорта г. Актау")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/health", tags=["service"])
def health(db: Session = Depends(get_db)):
    """Жив ли сервис и доступна ли БД с PostGIS. 503 — если БД недоступна."""
    try:
        postgis = db.execute(text("SELECT PostGIS_Lib_Version()")).scalar()
        return {"status": "ok", "db": "ok", "postgis": postgis, "env": settings.app_env}
    except Exception as exc:  # noqa: BLE001 — health должен ответить при любой ошибке БД
        return JSONResponse(status_code=503,
                            content={"status": "degraded", "db": "unavailable", "error": type(exc).__name__})


app.include_router(weather.router)
app.include_router(districts.router)
app.include_router(cooling_points.router)
app.include_router(reports.router)
app.include_router(route.router)
app.include_router(admin.router)
