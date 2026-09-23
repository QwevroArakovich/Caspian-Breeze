"""CoolPath: OSRM подменяется фейком, тепловая оценка идёт на реальной PostGIS с seed-данными."""
from app.services import routing

START = (43.6480, 51.1780)   # 6 мкр, в глубине
END = (43.6420, 51.1600)     # 2 мкр, у моря

# Вариант «по жаре»: напрямую через внутренние кварталы
HOT_LINE = [(51.1780, 43.6480), (51.1690, 43.6450), (51.1600, 43.6420)]
# Вариант «через бульвар и набережную»: заметно длиннее, но в тени и на бризе
COOL_LINE = [(51.1780, 43.6480), (51.1740, 43.6430), (51.1720, 43.6380), (51.1650, 43.6358), (51.1600, 43.6420)]


def fake_osrm(points, alternatives):
    if alternatives:
        return [{"coords": HOT_LINE, "distance": 1700.0}, {"coords": COOL_LINE, "distance": 2150.0}]
    return [{"coords": [(lon, lat) for lat, lon in points], "distance": 2600.0}]


def test_cool_route_recommends_cooler_option(client, monkeypatch):
    monkeypatch.setattr(routing, "osrm_routes", fake_osrm)
    r = client.post("/api/route/cool", json={"from": START, "to": END, "scenario": "heatwave"})
    assert r.status_code == 200, r.text
    data = r.json()
    routes = {x["label"]: x for x in data["routes"]}
    hot, cool = routes["Кратчайший"], routes["Альтернатива 1"]

    assert all(0 <= x["heat_exposure"] <= 100 for x in data["routes"])
    assert any(x["kind"] == "via_cooling" for x in data["routes"]), "должен быть вариант через точку охлаждения"
    assert cool["heat_exposure"] < hot["heat_exposure"]
    assert cool["shade_share_pct"] > hot["shade_share_pct"]
    assert any(s["type"] == "embankment" for s in cool["rest_stops"])

    rec = next(x for x in data["routes"] if x["recommended"])
    assert rec["id"] == data["recommended_id"]
    shortest = min(data["routes"], key=lambda x: x["distance_m"])
    assert rec["distance_m"] <= shortest["distance_m"] * 1.3 + 1
    assert rec["heat_exposure"] <= shortest["heat_exposure"]
    assert rec["label"] == "Альтернатива 1", "маршрут у набережной длиннее на 26 % — в пределах 30 %, и он прохладнее"
    assert "меньше солнца" in data["comparison"]["text"]
    assert data["heat_factor"] > 1 and data["weather_source"] == "simulation"


def test_cool_route_fallback_and_validation(client, monkeypatch):
    monkeypatch.setattr(routing, "osrm_routes", lambda points, alternatives: [])
    r = client.post("/api/route/cool", json={"from": START, "to": END, "scenario": "heatwave"})
    assert r.status_code == 200
    assert {x["source"] for x in r.json()["routes"]} == {"straight"}

    assert client.post("/api/route/cool", json={"from": START, "to": [43.30, 50.90]}).status_code == 422
    assert client.post("/api/route/cool", json={"from": START, "to": [43.6481, 51.1781]}).status_code == 422
