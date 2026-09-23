# Деплой Caspian Breeze

Схема: **backend + PostgreSQL/PostGIS — Render** (или Railway), **frontend — Vercel**.
Бесплатных тарифов хватает. Секреты (токен акимата) вводите только в дашбордах сервисов — не в код и не в чат.

Порядок важен: сначала backend (нужен его адрес для фронтенда), потом frontend, потом CORS.

---

## 0. Подготовка (2 мин)

1. Убедитесь, что последняя версия запушена в GitHub (`git push origin main`).
2. Придумайте токен акимата — длинная случайная строка. Сгенерировать можно так:
   - PowerShell: `[guid]::NewGuid().ToString("N")`
   - Python: `python -c "import secrets; print(secrets.token_urlsafe(24))"`

   Сохраните его в менеджере паролей. Токены `change-me` и `aktau2026` на проде запрещены — сервис не запустится.

---

## 1. Backend + база на Render (≈ 10 мин, из них 5–7 — сборка)

1. Зайдите на https://dashboard.render.com и войдите через GitHub.
2. **New +** → **Blueprint**.
3. Подключите репозиторий `QwevroArakovich/Caspian-Breeze` (при первом разе — **Configure account** → дать Render доступ к репозиторию).
4. Render прочитает `render.yaml` и покажет: базу `caspian-db` и сервис `caspian-breeze-api`.
   Он попросит значения двух переменных:
   - `ADMIN_TOKEN` — ваш токен из шага 0;
   - `CORS_ORIGINS` — пока впишите `http://localhost:5173` (заменим после Vercel).
5. **Apply** (или **Deploy Blueprint**). Сначала создастся база, потом соберётся Docker-образ.
6. Откройте сервис `caspian-breeze-api` → вкладка **Logs**. Успешный старт выглядит так:
   ```
   Running upgrade  -> 0001_initial …
   Running upgrade 0001_initial -> 0002_seed_support …
   districts: 15 · cooling_points: 49 (без микрорайона: 0) · reports добавлено: 42 …
   Uvicorn running on http://0.0.0.0:10000
   ```
7. Скопируйте адрес сервиса вверху страницы (вида `https://caspian-breeze-api.onrender.com`)
   и откройте `…/health` — должно быть `"db":"ok","postgis":"3.x"`. Документация API — `…/docs`.

**Если в логах ошибка про `postgis` (extension is not available / permission denied)** — переходите на Railway (раздел 1б).

### 1б. Альтернатива: Railway

1. https://railway.com → **New Project** → **Deploy a Template** → найдите **PostGIS** → **Deploy**.
2. В том же проекте: **+ Create** (или **+ New**) → **GitHub Repo** → `Caspian-Breeze`.
3. Откройте новый сервис → **Settings** → **Root Directory**: `backend` (Railway найдёт `Dockerfile` и `railway.json`).
4. **Variables** → добавьте:
   - `DATABASE_URL` = `${{PostGIS.DATABASE_URL}}` — ссылка на переменную базы; имя сервиса базы должно совпадать
     с тем, что в левой панели (если он называется иначе, выберите его через подсказку **Add Reference**);
   - `APP_ENV` = `production`
   - `ADMIN_TOKEN` = ваш токен
   - `CORS_ORIGINS` = `http://localhost:5173` (заменим после Vercel)
5. **Settings** → **Networking** → **Generate Domain**. Это адрес backend.
6. Дождитесь деплоя (**Deployments** → зелёный статус) и проверьте `…/health`.

---

## 2. Frontend на Vercel (≈ 3 мин)

1. https://vercel.com → войдите через GitHub → **Add New…** → **Project**.
2. **Import** репозиторий `Caspian-Breeze`.
3. **Root Directory** → **Edit** → выберите `frontend`. Framework Preset определится как **Vite**.
4. **Environment Variables**: `VITE_API_URL` = адрес backend из шага 1 **без** слеша в конце
   (например `https://caspian-breeze-api.onrender.com`).
   Без этой переменной сборка специально падает с понятной ошибкой.
5. **Deploy**. Через минуту получите адрес вида `https://caspian-breeze.vercel.app`.

---

## 3. Связать фронтенд и backend (CORS, 2 мин)

1. Render → сервис `caspian-breeze-api` → **Environment** → `CORS_ORIGINS` =
   `https://caspian-breeze.vercel.app` (ваш точный домен Vercel, без слеша; можно несколько через запятую,
   например добавить `http://localhost:5173` для локальной разработки).
   На Railway — то же в **Variables**.
2. **Save Changes** — сервис перезапустится сам (Render: **Save, rebuild, and deploy**).
3. Нужны превью-деплои Vercel? Добавьте `CORS_ORIGIN_REGEX` = `https://caspian-breeze-.*\.vercel\.app`.

---

## 4. Проверка демо-сценария (2 мин)

На своём компьютере, в папке проекта:

```powershell
$env:ADMIN_TOKEN="ваш-токен"
python scripts/smoke_test.py --api https://caspian-breeze-api.onrender.com --web https://caspian-breeze.vercel.app
```

Скрипт пройдёт весь сценарий из CONTEXT.md: погода → микрорайоны → ближайшая прохлада → CoolPath →
заявка «Здесь нет тени» → рост индекса → акимат ставит «Запланировано» → житель видит статус → CSV → CORS →
открываются `/` и `/admin`. Тестовую заявку он в конце отклоняет.
Пришлите вывод в чат (токена в нём нет) — разберём, если что-то красное.

Потом руками: откройте сайт с телефона, нажмите «Маршрут в тени», отправьте заявку, в `/admin` смените статус.

---

## 5. Перед питчем

- **Разбудите backend за 5 минут до выступления.** Бесплатный Render засыпает после 15 минут без запросов,
  первый запрос после сна идёт ~50 секунд. Откройте сайт и `/admin` и держите вкладки открытыми —
  опрос каждые 30 с не даст ему уснуть.
- **Демо-данные со свежими датами:** Render → сервис → **Shell** → `python -m seed.seed --reset-reports`
  (заявки жителей не трогает, пересоздаёт только демо).
- **Демо-режим жары:** `https://…vercel.app/?scenario=heatwave` — в сентябре в Актау прохладно, а показать нужно июль.
- Бесплатная база Render живёт 30 дней — для хакатона достаточно.

## Переменные окружения backend

| Переменная | Обязательна | Пример | Зачем |
|---|---|---|---|
| `DATABASE_URL` | да | задаёт Render/Railway | PostgreSQL с PostGIS; `postgres://` приводится к драйверу psycopg автоматически |
| `ADMIN_TOKEN` | да | длинная случайная строка | вход в `/admin`, заголовок `X-Admin-Token` |
| `CORS_ORIGINS` | да | `https://caspian-breeze.vercel.app` | с каких сайтов браузеру можно ходить в API |
| `CORS_ORIGIN_REGEX` | нет | `https://caspian-breeze-.*\.vercel\.app` | превью-деплои Vercel |
| `APP_ENV` | да | `production` | в проде запрещает токен по умолчанию |
| `OSRM_URL` | нет | `https://routing.openstreetmap.de/routed-foot` | пешеходные маршруты |
| `PORT` | нет | задаёт платформа | порт uvicorn |
