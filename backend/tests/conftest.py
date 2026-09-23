"""
Тесты идут на реальной PostgreSQL + PostGIS (та же БД, что в .env / DATABASE_URL).
Каждый тест выполняется внутри транзакции, которая откатывается в конце:
созданные тестом заявки и смены статусов в БД не остаются.
"""
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import engine, get_db
from app.main import app
from app.services import weather as weather_service

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(scope="session", autouse=True)
def prepared_db():
    """Миграции + seed-данные Актау (оба идемпотентны)."""
    command.upgrade(Config("alembic.ini"), "head")
    from seed.seed import seed_cooling_points, seed_districts, seed_reports
    with Session(engine) as db, db.begin():
        seed_districts(db)
        seed_cooling_points(db)
        seed_reports(db, reset=False)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_token", ADMIN_TOKEN)
    weather_service.clear_cache()
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer.rollback()
        connection.close()
        weather_service.clear_cache()
