"""Статистика микрорайонов для карты жителя и панели акимата — один запрос, один расчёт индекса."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.index import DistrictFactors, shade_deficit_index

DISTRICTS_SQL = text("""
SELECT d.id, d.name, d.population, d.green_ratio, d.heat_index_base,
       ST_AsGeoJSON(d.geom, 6)::json AS geometry,
       ST_Area(d.geom::geography) / 1e6 AS area_km2,
       count(r.id) FILTER (WHERE r.status IN ('new', 'in_review', 'planned')) AS open_reports,
       count(r.id) FILTER (WHERE r.status IN ('new', 'in_review', 'planned') AND r.type = 'no_shade') AS open_no_shade,
       count(r.id) FILTER (WHERE r.status IN ('new', 'in_review', 'planned') AND r.type = 'need_fountain') AS open_need_fountain,
       count(r.id) FILTER (WHERE r.status IN ('new', 'in_review', 'planned') AND r.type = 'broken_ac') AS open_broken_ac,
       count(r.id) FILTER (WHERE r.status IN ('new', 'in_review', 'planned') AND r.type = 'other') AS open_other,
       (SELECT count(*) FROM cooling_points c WHERE c.district_id = d.id) AS cooling_points
FROM districts d
LEFT JOIN reports r ON r.district_id = d.id
GROUP BY d.id
ORDER BY d.id
""")


def district_stats(db: Session) -> list[dict]:
    rows = [dict(r) for r in db.execute(DISTRICTS_SQL).mappings()]
    for r in rows:
        r["cooling_density_km2"] = r["cooling_points"] / r["area_km2"] if r["area_km2"] else 0.0
    index = shade_deficit_index([
        DistrictFactors(id=r["id"], heat_index_base=r["heat_index_base"], green_ratio=r["green_ratio"],
                        open_reports=r["open_reports"], cooling_density=r["cooling_density_km2"])
        for r in rows
    ])
    for r in rows:
        r["shade_deficit_index"] = index[r["id"]]["index"]
        r["index_components"] = index[r["id"]]["components"]
    return rows
