from app.services import weather as weather_service
from app.services.index import DistrictFactors, shade_deficit_index
from tests.conftest import ADMIN_TOKEN

# Точка в центре 27 мкр (seed/generate_data.py)
LAT_27, LON_27 = 43.668, 51.195


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok" and r.json()["postgis"]


def test_shade_deficit_formula():
    """Формула из services/index.py пересчитывается вручную."""
    res = shade_deficit_index([
        DistrictFactors(id=1, heat_index_base=0.9, green_ratio=0.05, open_reports=12, cooling_density=1.0),
        DistrictFactors(id=2, heat_index_base=0.4, green_ratio=0.40, open_reports=0, cooling_density=4.0),
    ])
    # 100·(0.4·0.9 + 0.25·0.95 + 0.2·12/12 + 0.15·(1 − 1/4)) = 36 + 23.75 + 20 + 11.25 = 91
    assert res[1]["index"] == 91.0
    # 100·(0.4·0.4 + 0.25·0.6 + 0 + 0) = 16 + 15 = 31
    assert res[2]["index"] == 31.0
    assert round(sum(res[1]["components"].values()), 1) == res[1]["index"]
    # Лидер тоже реагирует на новую жалобу: 6 → 7 открытых заявок поднимают индекс на 100·0.2/12 ≈ 1.7
    six = shade_deficit_index([DistrictFactors(3, 0.9, 0.05, 6, 1.0), DistrictFactors(4, 0.4, 0.4, 0, 4.0)])[3]["index"]
    seven = shade_deficit_index([DistrictFactors(3, 0.9, 0.05, 7, 1.0), DistrictFactors(4, 0.4, 0.4, 0, 4.0)])[3]["index"]
    assert round(seven - six, 1) == 1.7


def test_districts_geojson_and_index(client):
    fc = client.get("/api/districts").json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) >= 12
    by_name = {f["properties"]["name"]: f for f in fc["features"]}
    assert all(f["geometry"]["type"] == "Polygon" for f in fc["features"])
    assert all(0 <= f["properties"]["shade_deficit_index"] <= 100 for f in fc["features"])
    hot = sum(by_name[n]["properties"]["shade_deficit_index"] for n in ("27 мкр", "28 мкр", "29 мкр")) / 3
    coastal = sum(by_name[n]["properties"]["shade_deficit_index"] for n in ("1 мкр", "3 мкр", "5 мкр")) / 3
    assert hot > coastal + 20, "новые внутренние мкр должны быть заметно горячее прибрежных"


def test_cooling_points_filters_and_nearest(client):
    parks = client.get("/api/cooling-points", params={"type": "park"}).json()["features"]
    assert parks and all(f["properties"]["type"] == "park" for f in parks)

    bbox = "51.14,43.63,51.17,43.65"  # старый центр у моря
    in_box = client.get("/api/cooling-points", params={"bbox": bbox}).json()["features"]
    assert in_box and all(51.14 <= f["geometry"]["coordinates"][0] <= 51.17 for f in in_box)

    near = client.get("/api/cooling-points/nearest", params={"lat": LAT_27, "lon": LON_27, "limit": 5}).json()
    dists = [f["properties"]["distance_m"] for f in near["features"]]
    assert len(dists) == 5 and dists == sorted(dists) and dists[0] < 500

    assert client.get("/api/cooling-points", params={"type": "casino"}).status_code == 422


def test_create_report_assigns_district(client):
    r = client.post("/api/reports", json={"type": "no_shade", "comment": "Нет навеса у школы",
                                          "lat": LAT_27, "lon": LON_27})
    assert r.status_code == 201
    f = r.json()
    assert f["properties"]["district_name"] == "27 мкр"
    assert f["properties"]["status"] == "new" and f["properties"]["source"] == "form"
    assert f["properties"]["history"][0]["new_status"] == "new"
    # точка в Каспийском море далеко от города — вне допустимой области
    assert client.post("/api/reports", json={"type": "other", "lat": 43.3, "lon": 50.9}).status_code == 422


def test_status_change_requires_token_and_logs(client):
    rid = client.post("/api/reports", json={"type": "need_fountain", "lat": LAT_27, "lon": LON_27}).json()["id"]
    body = {"status": "planned", "note": "Фонтанчик включён в план"}

    assert client.patch(f"/api/reports/{rid}/status", json=body).status_code == 401
    assert client.patch(f"/api/reports/{rid}/status", json=body,
                        headers={"X-Admin-Token": "wrong"}).status_code == 401

    r = client.patch(f"/api/reports/{rid}/status", json=body, headers={"X-Admin-Token": ADMIN_TOKEN})
    assert r.status_code == 200
    history = r.json()["properties"]["history"]
    assert [h["new_status"] for h in history] == ["new", "planned"]
    assert history[-1]["old_status"] == "new" and history[-1]["note"] == body["note"]

    planned = client.get("/api/reports", params={"status": "planned"}).json()["features"]
    assert rid in [f["id"] for f in planned]
    assert all(f["properties"]["status"] == "planned" for f in planned)


def test_heatmap_and_weather(client, monkeypatch):
    heat = client.get("/api/reports/heatmap").json()
    assert heat and all(len(p) == 3 and 0 < p[2] <= 1 for p in heat)

    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return {
            "current": {"temperature_2m": 38.0, "apparent_temperature": 40.5,
                        "wind_speed_10m": 5.0, "relative_humidity_2m": 20},
            "hourly": {"time": [f"2026-07-15T{h:02d}:00" for h in range(12, 24)],
                       "temperature_2m": [38.0] * 12, "apparent_temperature": [40.5] * 12, "uv_index": [9.0] * 12},
        }

    monkeypatch.setattr(weather_service, "_fetch_open_meteo", fake_fetch)
    first = client.get("/api/weather").json()
    second = client.get("/api/weather").json()
    assert first["heat_level"] == "extreme" and len(first["hourly"]) == 12
    assert second["cached"] is True and calls["n"] == 1, "второй запрос должен прийти из кеша"
    assert client.get("/api/weather", params={"scenario": "heatwave"}).json()["source"] == "simulation"


def test_report_from_coolpath_and_lookup(client):
    """Заявка «Здесь нет тени» из маршрута и страница «Мои заявки» по номеру."""
    r = client.post("/api/reports", json={"type": "no_shade", "lat": LAT_27, "lon": LON_27, "source": "coolpath",
                                          "comment": "Маршрут 27 мкр → Набережная: открытый участок"})
    assert r.status_code == 201 and r.json()["properties"]["source"] == "coolpath"
    rid = r.json()["id"]
    got = client.get(f"/api/reports/{rid}").json()
    assert got["properties"]["district_name"] == "27 мкр"
    assert [h["new_status"] for h in got["properties"]["history"]] == ["new"]
    assert client.get("/api/reports/99999999").status_code == 404
