import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, GeoJSON, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, ZoomControl, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { CoolRoute, CoolingPoint, CoolingPoints, CoolingType, Districts, HeatPoint, LatLon, Reports } from "../api";
import { AKTAU_CENTER, AKTAU_ZOOM, POINT_TYPES, REPORT_STATUSES, REPORT_TYPES, indexColor, routeColors } from "../lib/meta";
import HeatLayer from "./HeatLayer";
import type { Layers } from "./LayerPanel";

type Props = {
  layers: Layers;
  districts: Districts | null;
  points: CoolingPoints | null;
  heat: HeatPoint[] | null;
  picking: boolean;
  onMapPick: (lat: number, lon: number) => void;
  me: [number, number] | null;
  nearestIds: Set<number>;
  selected: CoolingPoint | null;
  route: { from: LatLon | null; to: LatLon | null; result: CoolRoute | null; selectedId: number | null } | null;
  reports: Reports | null;
  highlightReportId: number | null;
  reportPoint: LatLon | null;
  focus: LatLon | null;
  onHotspotClick: () => void;
};

const iconCache = new Map<string, L.DivIcon>();
function iconFor(type: CoolingType, near: boolean): L.DivIcon {
  const key = `${type}:${near}`;
  if (!iconCache.has(key)) {
    const size = near ? 34 : 26;
    iconCache.set(
      key,
      L.divIcon({
        className: "",
        html: `<div class="cb-emoji-icon${near ? " is-near" : ""}" style="width:${size}px;height:${size}px">${POINT_TYPES[type].emoji}</div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2],
      }),
    );
  }
  return iconCache.get(key)!;
}

const endIcon = (letter: string, bg: string) =>
  L.divIcon({
    className: "",
    html: `<div style="width:28px;height:28px;border-radius:50%;background:${bg};color:#fff;border:3px solid #fff;display:grid;place-items:center;font:800 13px Onest,sans-serif;box-shadow:0 1px 4px rgb(0 0 0/.3)">${letter}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
const startIcon = endIcon("А", "#43360F");
const finishIcon = endIcon("Б", "#23868A");

const youIcon = L.divIcon({ className: "", html: '<div class="cb-you"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });

function ClickCatcher({ enabled, onPick }: { enabled: boolean; onPick: (lat: number, lon: number) => void }) {
  const map = useMapEvents({
    click(e) {
      if (enabled) onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  useEffect(() => {
    map.getContainer().style.cursor = enabled ? "crosshair" : "";
  }, [enabled, map]);
  return null;
}

/** Подгоняет карту под «я + 5 ближайших» и перелетает к выбранной точке */
function Camera({ me, nearest, selected }: { me: [number, number] | null; nearest: CoolingPoint[]; selected: CoolingPoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (!me || nearest.length === 0) return;
    const bounds = L.latLngBounds([me, ...nearest.map((p) => [p.geometry.coordinates[1], p.geometry.coordinates[0]] as [number, number])]);
    // Снизу панель результатов: на телефоне она занимает почти половину экрана, на десктопе — левую колонку
    const { x: w, y: h } = map.getSize();
    const mobile = w < 768;
    map.fitBounds(bounds, {
      paddingTopLeft: [mobile ? 32 : 440, mobile ? 130 : 60],
      paddingBottomRight: [32, mobile ? Math.round(h * 0.5) : 60],
      maxZoom: 16,
    });
  }, [map, me, nearest]);
  useEffect(() => {
    if (!selected) return;
    const [lon, lat] = selected.geometry.coordinates;
    map.flyTo([lat, lon], Math.max(map.getZoom(), 16), { duration: 0.6 });
  }, [map, selected]);
  return null;
}

/** При первой загрузке вписывает все микрорайоны в экран (с отступом под плашку погоды) */
function FitCity({ districts }: { districts: Districts | null }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (!districts || done.current || districts.features.length === 0) return;
    done.current = true;
    const layer = L.geoJSON(districts as unknown as GeoJSON.FeatureCollection);
    map.fitBounds(layer.getBounds(), { paddingTopLeft: [16, 180], paddingBottomRight: [16, 90] });
  }, [map, districts]);
  return null;
}

/** На отдалении иконки меньше, чтобы город не превращался в россыпь эмодзи */
function ZoomClass() {
  const map = useMapEvents({
    zoomend() {
      map.getContainer().classList.toggle("cb-zoom-low", map.getZoom() < 15);
    },
  });
  useEffect(() => {
    map.getContainer().classList.toggle("cb-zoom-low", map.getZoom() < 15);
  }, [map]);
  return null;
}

const pinIcon = L.divIcon({
  className: "",
  html: '<div style="font-size:30px;line-height:30px;filter:drop-shadow(0 1px 2px rgb(0 0 0/.35))">📍</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 28],
});

/** Перелёт к точке (новая заявка, «Показать на карте») */
function FocusCamera({ focus }: { focus: LatLon | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo(focus, Math.max(map.getZoom(), 16), { duration: 0.6 });
  }, [map, focus]);
  return null;
}

/** Вписывает все варианты маршрута, когда пришёл новый результат */
function RouteCamera({ result }: { result: CoolRoute | null }) {
  const map = useMap();
  useEffect(() => {
    if (!result) return;
    const all = result.routes.flatMap((r) => r.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]));
    const { x: w, y: h } = map.getSize();
    const mobile = w < 768;
    map.fitBounds(L.latLngBounds(all), {
      paddingTopLeft: [mobile ? 24 : 440, mobile ? 130 : 60],
      paddingBottomRight: [24, mobile ? Math.round(h * 0.55) : 60],
      maxZoom: 17,
    });
  }, [map, result]);
  return null;
}

export default function MapView({
  layers,
  districts,
  points,
  heat,
  picking,
  onMapPick,
  me,
  nearestIds,
  selected,
  route,
  reports,
  highlightReportId,
  reportPoint,
  focus,
  onHotspotClick,
}: Props) {
  const colors = route?.result ? routeColors(route.result.routes) : {};
  const activeRoute = route?.result?.routes.find((r) => r.id === route.selectedId) ?? null;
  const toLatLngs = (coords: [number, number][]) => coords.map(([lon, lat]) => [lat, lon] as [number, number]);
  const visiblePoints = useMemo(
    () => (points?.features ?? []).filter((p) => layers[POINT_TYPES[p.properties.type].group] || nearestIds.has(p.id)),
    [points, layers, nearestIds],
  );
  const nearest = useMemo(
    () => (points?.features ?? []).filter((p) => nearestIds.has(p.id)),
    [points, nearestIds],
  );

  return (
    <MapContainer center={AKTAU_CENTER} zoom={AKTAU_ZOOM} zoomSnap={0.5} zoomControl={false} className="h-full w-full" attributionControl>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        maxZoom={19}
      />
      <ZoomControl position="bottomright" />

      {layers.districts && districts && (
        <GeoJSON
          key={districts.features.map((f) => `${f.id}:${f.properties.shade_deficit_index}`).join()}
          data={districts as unknown as GeoJSON.FeatureCollection}
          style={(f) => {
            const v = (f?.properties as { shade_deficit_index: number }).shade_deficit_index;
            return { color: "#fff", weight: 1.5, fillColor: indexColor(v), fillOpacity: 0.42 };
          }}
          onEachFeature={(f, layer) => {
            const p = f.properties as Districts["features"][number]["properties"];
            const c = p.index_components;
            layer.bindTooltip(`${p.name}: ${p.shade_deficit_index}`, { sticky: true });
            layer.bindPopup(
              `<b>${p.name}</b><br>Нехватка тени: <b>${p.shade_deficit_index}</b> из 100<br>` +
                `<small>нагрев ${c.heat} · мало зелени ${c.no_green} · жалобы ${c.reports} · мало укрытий ${c.no_cooling}</small><br>` +
                `Зелень: ${Math.round(p.green_ratio * 100)} % · точек охлаждения: ${p.cooling_points} · открытых жалоб: ${p.open_reports}`,
            );
          }}
        />
      )}

      {layers.heatmap && heat && heat.length > 0 && <HeatLayer points={heat} />}

      {/* Заявки жителей: цвет — статус; выделенная (только что отправленная / найденная) — крупнее */}
      {reports?.features
        .filter((r) => layers.reports || r.id === highlightReportId)
        .map((r) => {
          const [lon, lat] = r.geometry.coordinates;
          const st = REPORT_STATUSES[r.properties.status];
          const hl = r.id === highlightReportId;
          return (
            <CircleMarker
              key={`rep${r.id}:${r.properties.status}:${hl}`}
              center={[lat, lon]}
              radius={hl ? 11 : 6}
              pathOptions={{ color: hl ? "#43360F" : "#fff", weight: hl ? 3 : 1.5, fillColor: st.color, fillOpacity: 0.95 }}
            >
              <Popup>
                <b>Заявка №{r.id}</b>
                <br />
                {REPORT_TYPES[r.properties.type].label}
                <br />
                {r.properties.district_name ?? ""} · <b>{st.label}</b>
                {r.properties.comment && (
                  <>
                    <br />
                    <i>{r.properties.comment}</i>
                  </>
                )}
              </Popup>
            </CircleMarker>
          );
        })}

      {visiblePoints.map((p) => {
        const [lon, lat] = p.geometry.coordinates;
        const meta = POINT_TYPES[p.properties.type];
        return (
          <Marker key={p.id} position={[lat, lon]} icon={iconFor(p.properties.type, nearestIds.has(p.id))} title={p.properties.name}>
            <Popup>
              <b>{p.properties.name}</b>
              <br />
              {meta.label}
              {p.properties.hours && (
                <>
                  <br />
                  {p.properties.hours}
                </>
              )}
              <br />
              <small>{p.properties.is_verified ? "Проверено командой" : "Демо-объект, адрес уточняется"}</small>
            </Popup>
          </Marker>
        );
      })}

      {selected && (
        <Popup position={[selected.geometry.coordinates[1], selected.geometry.coordinates[0]]} offset={[0, -14]}>
          <b>{selected.properties.name}</b>
          <br />
          {POINT_TYPES[selected.properties.type].label}
        </Popup>
      )}

      {me && <Marker position={me} icon={youIcon} title="Вы здесь" zIndexOffset={1000} />}

      {/* CoolPath: сначала неактивные варианты (пунктир), поверх — выбранный */}
      {route?.result?.routes
        .filter((r) => r.id !== route.selectedId)
        .map((r) => (
          <Polyline
            key={`r${r.id}`}
            positions={toLatLngs(r.geometry.coordinates)}
            pathOptions={{ color: colors[r.id], weight: 5, opacity: 0.75, dashArray: "8 10", lineCap: "round" }}
          >
            <Tooltip sticky>{r.label}: солнце {Math.round(r.heat_exposure)}/100</Tooltip>
          </Polyline>
        ))}
      {activeRoute && (
        <>
          <Polyline
            positions={toLatLngs(activeRoute.geometry.coordinates)}
            pathOptions={{ color: "#fff", weight: 11, opacity: 0.9, lineCap: "round", lineJoin: "round" }}
          />
          <Polyline
            positions={toLatLngs(activeRoute.geometry.coordinates)}
            pathOptions={{ color: colors[activeRoute.id], weight: 7, opacity: 1, lineCap: "round", lineJoin: "round" }}
          />
          {activeRoute.rest_stops.map((s) => (
            <Marker key={`s${s.id}`} position={[s.lat, s.lon]} icon={iconFor(s.type, true)} title={s.name} zIndexOffset={500}>
              <Popup>
                <b>{s.name}</b>
                <br />
                Точка отдыха на маршруте
              </Popup>
            </Marker>
          ))}
          {activeRoute.hottest_point && (
            <CircleMarker
              center={[activeRoute.hottest_point.lat, activeRoute.hottest_point.lon]}
              radius={14}
              pathOptions={{ color: "#C8412B", weight: 3, fillColor: "#C8412B", fillOpacity: 0.2 }}
              eventHandlers={{ click: onHotspotClick }}
            >
              <Tooltip>Самый открытый участок — нажмите, чтобы сообщить</Tooltip>
            </CircleMarker>
          )}
        </>
      )}
      {reportPoint && <Marker position={reportPoint} icon={pinIcon} title="Место проблемы" zIndexOffset={1100} />}
      {route?.from && <Marker position={route.from} icon={startIcon} title="Старт" zIndexOffset={900} />}
      {route?.to && <Marker position={route.to} icon={finishIcon} title="Финиш" zIndexOffset={900} />}

      <ClickCatcher enabled={picking} onPick={onMapPick} />
      <FitCity districts={districts} />
      <ZoomClass />
      <RouteCamera result={route?.result ?? null} />
      <FocusCamera focus={focus} />
      <Camera me={me} nearest={nearest} selected={selected} />
    </MapContainer>
  );
}
