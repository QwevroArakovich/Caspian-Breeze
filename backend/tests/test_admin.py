from app.services.recommend import recommend
from tests.conftest import ADMIN_TOKEN

H = {"X-Admin-Token": ADMIN_TOKEN}
LAT_27, LON_27 = 43.668, 51.195


def test_admin_requires_token(client):
    assert client.get("/api/admin/check").status_code == 401
    assert client.get("/api/admin/summary", headers={"X-Admin-Token": "nope"}).status_code == 401
    assert client.get("/api/admin/check", headers=H).json() == {"ok": True}


def test_recommendation_heuristic():
    calm = recommend(30, 0, 0, 0)
    assert calm["text"] == "Плановый мониторинг" and calm["priority"] == "low"
    hot = recommend(80, open_no_shade=3, open_need_fountain=2, open_broken_ac=1)
    # 3 базовых + ceil(3/2)=2 навеса; 1 + 2 фонтанчика; 1 ремонт
    assert (hot["shades"], hot["fountains"], hot["ac_repairs"], hot["priority"]) == (5, 3, 1, "high")
    assert hot["text"] == "Установить 5 навесов, 3 фонтанчика, отремонтировать 1 кондиционер"


def test_summary_reacts_to_new_report_and_csv(client):
    before = client.get("/api/admin/summary", headers=H).json()
    d27 = next(d for d in before["districts"] if d["name"] == "27 мкр")
    assert len(before["daily"]) == 30 and before["kpi"]["top_districts"][0]["shade_deficit_index"] >= d27["shade_deficit_index"] - 0.01

    rid = client.post("/api/reports", json={"type": "need_fountain", "lat": LAT_27, "lon": LON_27}).json()["id"]
    after = client.get("/api/admin/summary", headers=H).json()
    d27_after = next(d for d in after["districts"] if d["name"] == "27 мкр")
    assert after["kpi"]["open_reports"] == before["kpi"]["open_reports"] + 1
    assert d27_after["open_by_type"]["need_fountain"] == d27["open_by_type"]["need_fountain"] + 1
    assert d27_after["recommendation"]["fountains"] == d27["recommendation"]["fountains"] + 1
    assert d27_after["shade_deficit_index"] > d27["shade_deficit_index"], "новая жалоба должна поднять индекс района"

    client.patch(f"/api/reports/{rid}/status", json={"status": "planned", "note": "Фонтанчик в плане на октябрь"},
                 headers=H)
    csv_resp = client.get("/api/admin/reports.csv", headers=H, params={"status": "planned"})
    body = csv_resp.content.decode("utf-8")
    assert csv_resp.status_code == 200 and body.startswith("\ufeff№;Создана")
    line = next(l for l in body.splitlines() if l.startswith(f"{rid};"))
    assert "27 мкр" in line and "Запланировано" in line and "Фонтанчик в плане на октябрь" in line
    assert all(";Запланировано;" in l for l in body.splitlines()[1:])


def test_demo_reset_restores_initial_state(client):
    client.post("/api/reports", json={"type": "other", "lat": LAT_27, "lon": LON_27})
    assert client.post("/api/admin/demo/reset").status_code == 401
    r = client.post("/api/admin/demo/reset", headers=H)
    assert r.status_code == 200 and r.json()["demo_reports"] == 42 and r.json()["removed_user_reports"] >= 1
    all_reports = client.get("/api/reports", params={"limit": 2000}).json()["features"]
    assert len(all_reports) == 42 and {f["properties"]["source"] for f in all_reports} == {"seed"}
