"""
Проверка демо-сценария Caspian Breeze на задеплоенной версии (только стандартная библиотека Python).

    python scripts/smoke_test.py --api https://caspian-breeze-api.onrender.com --web https://caspian-breeze.vercel.app

Токен акимата скрипт берёт из переменной окружения ADMIN_TOKEN (вы задаёте её сами, в чат его не пишите):
    PowerShell:  $env:ADMIN_TOKEN="ваш-токен"; python scripts/smoke_test.py --api … --web …
    bash:        ADMIN_TOKEN=ваш-токен python scripts/smoke_test.py --api … --web …
Без токена шаги акимата пропускаются.

Скрипт создаёт одну тестовую заявку и в конце переводит её в «Отклонено» с пометкой smoke-test,
чтобы она не попадала на тепловую карту и в открытые.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

START_27 = [43.668, 51.195]          # 27 мкр — самый жаркий
EMBANKMENT_1 = [43.6355, 51.1650]    # Набережная Актау · 1 мкр

results: list[tuple[str, str, str]] = []  # (статус, шаг, детали)


def call(method: str, url: str, body=None, headers=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "User-Agent": "caspian-smoke-test", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def as_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def step(name: str):
    def deco(fn):
        def run(*a, **kw):
            t = time.time()
            try:
                status, detail = fn(*a, **kw)
            except Exception as exc:  # сеть, формат, assert
                status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
            results.append((status, name, f"{detail} ({time.time() - t:.1f} с)"))
            icon = {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌", "SKIP": "⏭️ "}[status]
            print(f"{icon} {name}: {detail}")
            return status
        return run
    return deco


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-тест демо-сценария Caspian Breeze")
    ap.add_argument("--api", required=True, help="адрес backend, например https://caspian-breeze-api.onrender.com")
    ap.add_argument("--web", help="адрес фронтенда, например https://caspian-breeze.vercel.app")
    args = ap.parse_args()
    api, web = args.api.rstrip("/"), (args.web or "").rstrip("/")
    token = os.environ.get("ADMIN_TOKEN")
    ctx: dict = {}

    @step("1. Backend жив, PostGIS на месте (первый запрос на бесплатном тарифе может идти ~1 мин)")
    def health():
        code, _, raw = call("GET", f"{api}/health", timeout=120)
        j = as_json(raw)
        assert code == 200 and j and j["db"] == "ok", f"HTTP {code}: {raw[:200]!r}"
        return "OK", f"PostGIS {j['postgis']}, env={j.get('env')}"

    @step("2. Погода Актау (реальная) и демо-жара")
    def weather():
        code, _, raw = call("GET", f"{api}/api/weather")
        sim = as_json(call("GET", f"{api}/api/weather?scenario=heatwave")[2])
        assert sim and sim["heat_level"] == "extreme", "симуляция жары не работает"
        if code != 200:
            return "WARN", f"Open-Meteo недоступен (HTTP {code}) — фронт покажет симуляцию"
        j = as_json(raw)
        return "OK", f"сейчас ощущается {j['feels_like']}°, уровень {j['heat_level']}; симуляция +41° работает"

    @step("3. Микрорайоны и индекс нехватки тени")
    def districts():
        fc = as_json(call("GET", f"{api}/api/districts")[2])
        feats = fc["features"]
        assert len(feats) >= 12, f"микрорайонов {len(feats)}"
        top = max(feats, key=lambda f: f["properties"]["shade_deficit_index"])
        ctx["districts"] = {f["properties"]["name"]: f["properties"] for f in feats}
        return "OK", f"{len(feats)} мкр, самый жаркий {top['properties']['name']} ({top['properties']['shade_deficit_index']})"

    @step("4. Точки охлаждения и «Ближайшая прохлада» из 27 мкр")
    def points():
        fc = as_json(call("GET", f"{api}/api/cooling-points")[2])
        near = as_json(call("GET", f"{api}/api/cooling-points/nearest?lat={START_27[0]}&lon={START_27[1]}&limit=5")[2])
        n = near["features"]
        assert len(fc["features"]) >= 40 and len(n) == 5
        return "OK", f"{len(fc['features'])} точек; ближайшая «{n[0]['properties']['name']}» в {n[0]['properties']['distance_m']:.0f} м"

    @step("5. CoolPath 27 мкр → Набережная 1 мкр")
    def route():
        code, _, raw = call("POST", f"{api}/api/route/cool",
                            {"from": START_27, "to": EMBANKMENT_1, "scenario": "heatwave"}, timeout=60)
        j = as_json(raw)
        assert code == 200, f"HTTP {code}: {raw[:200]!r}"
        rec = next(r for r in j["routes"] if r["recommended"])
        ctx["hot"] = rec["hottest_point"]
        detail = f"{len(j['routes'])} вар., рекомендован «{rec['label']}» ({rec['distance_m'] / 1000:.1f} км); {j['comparison']['text']}"
        if any(r["source"] == "straight" for r in j["routes"]):
            return "WARN", detail + " — OSRM не ответил, линии по прямой"
        if len(j["routes"]) < 2:
            return "WARN", detail + " — только один вариант"
        return "OK", detail

    @step("6. Житель: «Здесь нет тени» на самом открытом участке маршрута")
    def report():
        hp = ctx.get("hot") or {"lat": START_27[0], "lon": START_27[1]}
        before = ctx.get("districts", {})
        code, _, raw = call("POST", f"{api}/api/reports", {
            "type": "no_shade", "lat": hp["lat"], "lon": hp["lon"], "source": "coolpath",
            "comment": "smoke-test: проверка демо-сценария, можно удалить"})
        j = as_json(raw)
        assert code == 201, f"HTTP {code}: {raw[:200]!r}"
        ctx["rid"], name = j["id"], j["properties"]["district_name"]
        after = {f["properties"]["name"]: f["properties"] for f in as_json(call("GET", f"{api}/api/districts")[2])["features"]}
        grew = name in before and after[name]["open_reports"] == before[name]["open_reports"] + 1
        detail = f"заявка №{j['id']}, район {name}; индекс {before.get(name, {}).get('shade_deficit_index')} → {after.get(name, {}).get('shade_deficit_index')}"
        return ("OK" if grew else "WARN"), detail + ("" if grew else " — число открытых заявок района не выросло")

    @step("7. Акимат: вход по токену и «Запланирован навес»")
    def admin():
        if not token:
            return "SKIP", "задайте ADMIN_TOKEN в окружении, чтобы проверить панель"
        h = {"X-Admin-Token": token}
        code = call("GET", f"{api}/api/admin/check", headers=h)[0]
        assert code == 200, f"токен не принят (HTTP {code})"
        assert call("GET", f"{api}/api/admin/check", headers={"X-Admin-Token": "wrong"})[0] == 401, "неверный токен пропущен!"
        s = as_json(call("GET", f"{api}/api/admin/summary", headers=h)[2])
        code, _, raw = call("PATCH", f"{api}/api/reports/{ctx['rid']}/status",
                            {"status": "planned", "note": "smoke-test: навес включён в план"}, headers=h)
        assert code == 200, f"PATCH HTTP {code}: {raw[:200]!r}"
        return "OK", f"открытых заявок {s['kpi']['open_reports']}, топ — {s['kpi']['top_districts'][0]['name']}; статус сменён"

    @step("8. Житель видит новый статус в «Моих заявках»")
    def citizen_sees():
        if not token:
            return "SKIP", "нужен шаг 7"
        j = as_json(call("GET", f"{api}/api/reports/{ctx['rid']}")[2])
        hist = [h["new_status"] for h in j["properties"]["history"]]
        assert j["properties"]["status"] == "planned" and hist[-1] == "planned", f"история: {hist}"
        return "OK", f"статус «planned», история: {' → '.join(hist)}"

    @step("9. Экспорт CSV для благоустройства")
    def csv_export():
        if not token:
            return "SKIP", "нужен ADMIN_TOKEN"
        code, headers, raw = call("GET", f"{api}/api/admin/reports.csv?status=planned", headers={"X-Admin-Token": token})
        text = raw.decode("utf-8-sig")
        assert code == 200 and text.startswith("№;") and f"\n{ctx['rid']};" in text
        return "OK", f"{len(text.splitlines()) - 1} строк, заявка №{ctx['rid']} в файле"

    @step("10. CORS: браузер с домена фронтенда пустят к API")
    def cors():
        if not web:
            return "SKIP", "передайте --web, чтобы проверить CORS"
        code, headers, _ = call("OPTIONS", f"{api}/api/route/cool", headers={
            "Origin": web, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
        assert allowed in (web, "*"), f"API не разрешает {web} (ответ: {allowed}) — проверьте CORS_ORIGINS"
        return "OK", f"разрешён {allowed}"

    @step("11. Фронтенд: главная и /admin открываются")
    def frontend():
        if not web:
            return "SKIP", "передайте --web"
        for path in ("/", "/admin", "/?scenario=heatwave"):
            code, _, raw = call("GET", f"{web}{path}")
            assert code == 200 and b'<div id="root">' in raw, f"{path}: HTTP {code}"
        return "OK", "/, /admin и демо-режим отдают приложение"

    @step("12. Уборка: тестовая заявка → «Отклонено»")
    def cleanup():
        if not token or "rid" not in ctx:
            return "SKIP", "нечего убирать" if "rid" not in ctx else "без токена заявка останется «Новой» — отклоните её в /admin"
        code = call("PATCH", f"{api}/api/reports/{ctx['rid']}/status",
                    {"status": "rejected", "note": "smoke-test"}, headers={"X-Admin-Token": token})[0]
        assert code == 200
        return "OK", f"заявка №{ctx['rid']} отклонена и не мешает демо"

    print(f"API: {api}\nWEB: {web or '—'}\nТокен акимата: {'задан' if token else 'не задан'}\n")
    for fn in (health, weather, districts, points, route, report, admin, citizen_sees, csv_export, cors, frontend, cleanup):
        if fn() == "FAIL" and fn is health:
            print("\nBackend недоступен — дальше проверять нечего.")
            break

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\nИтого: {sum(r[0] == 'OK' for r in results)} OK, {len(warns)} предупреждений, {len(fails)} ошибок")
    for status, name, detail in fails + warns:
        print(f"  {'❌' if status == 'FAIL' else '⚠️ '} {name}\n     {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
