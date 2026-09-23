"""Настройки приложения из переменных окружения / файла .env."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://caspian:caspian@localhost:5432/caspian_breeze"
    # Точные адреса фронтенда через запятую: https://caspian-breeze.vercel.app,http://localhost:5173
    cors_origins: str = "http://localhost:5173"
    # Необязательно: регулярка для превью-деплоев Vercel, например https://caspian-breeze-.*\.vercel\.app
    cors_origin_regex: str | None = None
    admin_token: str = "change-me"
    app_env: str = "dev"
    # Пешеходный OSRM по графу OpenStreetMap (публичный сервер FOSSGIS); можно заменить на свой
    osrm_url: str = "https://routing.openstreetmap.de/routed-foot"
    # Кнопка «Демо-режим» в панели акимата (удаляет все заявки). На реальном внедрении — false
    demo_reset_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        """Render и Railway выдают postgres://… или postgresql://… — SQLAlchemy нужен явный драйвер psycopg."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
