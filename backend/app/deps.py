"""Общие зависимости FastAPI."""
import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Простая авторизация диспетчера акимата: заголовок X-Admin-Token из .env (ADMIN_TOKEN)."""
    expected = get_settings().admin_token
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный или отсутствующий X-Admin-Token")
