import { useMemo } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import type { Districts, HeatPoint, Reports } from "../api";
import HeatLayer from "../components/HeatLayer";
import { AKTAU_CENTER, INDEX_SCALE, REPORT_STATUSES, indexColor } from "../lib/meta";

const HEAT_WEIGHT = { new: 1, in_review: 1, planned: 0.7, done: 0.2, rejected: 0 } as const;

type Props = {
  districts: Districts | null;
  reports: Reports | null;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
};

export default function AdminMap({ districts, reports, selectedId, onSelect }: Props) {
  const heat = useMemo<HeatPoint[]>(
    () =>
      (reports?.features ?? [])
        .filter((r) => HEAT_WEIGHT[r.properties.status] > 0)
        .map((r) => [r.geometry.coordinates[1], r.geometry.coordinates[0], HEAT_WEIGHT[r.properties.status]]),
    [reports],
  );
  const open = (reports?.features ?? []).filter((r) => ["new", "in_review", "planned"].includes(r.properties.status));

  return (
    <section className="relative overflow-hidden rounded-2xl border border-line">
      <MapContainer center={AKTAU_CENTER} zoom={13} zoomSnap={0.5} className="h-[440px] w-full">
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" maxZoom={19} />
        {districts && (
          <GeoJSON
            key={`${districts.features.map((f) => f.properties.shade_deficit_index).join()}:${selectedId}`}
            data={districts as unknown as GeoJSON.FeatureCollection}
            style={(f) => {
              const id = (f as unknown as { id: number }).id;
              const v = (f?.properties as { shade_deficit_index: number }).shade_deficit_index;
              const sel = id === selectedId;
              return { color: sel ? "#43360F" : "#fff", weight: sel ? 3 : 1.5, fillColor: indexColor(v), fillOpacity: 0.5 };
            }}
            onEachFeature={(f, layer) => {
              const p = f.properties as { name: string; shade_deficit_index: number; open_reports: number };
              layer.bindTooltip(`${p.name}: индекс ${p.shade_deficit_index}, открытых заявок ${p.open_reports}`, { sticky: true });
              layer.on("click", () => onSelect((f as unknown as { id: number }).id));
            }}
          />
        )}
        {heat.length > 0 && <HeatLayer points={heat} />}
        {open.map((r) => (
          <CircleMarker
            key={`${r.id}:${r.properties.status}`}
            center={[r.geometry.coordinates[1], r.geometry.coordinates[0]]}
            radius={4}
            pathOptions={{ color: "#fff", weight: 1, fillColor: REPORT_STATUSES[r.properties.status].color, fillOpacity: 1 }}
          >
            <Tooltip>
              №{r.id} · {REPORT_STATUSES[r.properties.status].label}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="pointer-events-none absolute bottom-2 left-2 z-[500] rounded-lg bg-cream/95 px-2 py-1 text-[11px] shadow">
        <p className="mb-0.5 font-semibold">Индекс нехватки тени</p>
        <div className="flex overflow-hidden rounded">
          {INDEX_SCALE.map((s) => (
            <span key={s.label} className="px-1.5 py-0.5 font-semibold" style={{ background: s.color }}>
              {s.label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
