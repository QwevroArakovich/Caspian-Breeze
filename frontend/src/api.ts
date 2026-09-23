// Единая точка обращения к backend. Базовый URL задаётся переменной VITE_API_URL.
export const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000").replace(/\/$/, "");

// ── Типы ответов (зеркало app/schemas.py) ─────────────────────────────────────
export type HeatLevel = "normal" | "caution" | "danger" | "extreme";
export type CoolingType = "mall" | "ac_bus_stop" | "park" | "embankment" | "fountain" | "pharmacy" | "library";

export type Feature<G, P> = { type: "Feature"; id: number; geometry: G; properties: P };
export type FeatureCollection<G, P> = { type: "FeatureCollection"; features: Feature<G, P>[] };
export type PointGeom = { type: "Point"; coordinates: [number, number] };
export type PolygonGeom = { type: "Polygon"; coordinates: [number, number][][] };

export type HourlyWeather = { time: string; temperature: number; feels_like: number; uv_index: number };
export type Weather = {
  temperature: number;
  feels_like: number;
  uv_index: number;
  wind_speed: number;
  humidity: number;
  heat_level: HeatLevel;
  advice: string;
  hourly: HourlyWeather[];
  source: "open-meteo" | "simulation";
  fetched_at: string;
  cached: boolean;
  stale: boolean;
};

export type DistrictProps = {
  name: string;
  population: number | null;
  green_ratio: number;
  heat_index_base: number;
  area_km2: number;
  open_reports: number;
  cooling_points: number;
  cooling_density_km2: number;
  shade_deficit_index: number;
  index_components: { heat: number; no_green: number; reports: number; no_cooling: number };
};

export type CoolingPointProps = {
  name: string;
  type: CoolingType;
  hours: string | null;
  is_verified: boolean;
  district_id: number | null;
  district_name: string | null;
  distance_m: number | null;
};

export type ReportType = "no_shade" | "need_fountain" | "broken_ac" | "other";
export type ReportStatus = "new" | "in_review" | "planned" | "done" | "rejected";
export type StatusLogEntry = { old_status: ReportStatus | null; new_status: ReportStatus; note: string | null; changed_at: string };
export type ReportProps = {
  type: ReportType;
  comment: string | null;
  status: ReportStatus;
  source: "seed" | "form" | "coolpath";
  district_id: number | null;
  district_name: string | null;
  created_at: string;
  updated_at: string;
  photo_url: string | null;
  history: StatusLogEntry[] | null;
};
export type Report = Feature<PointGeom, ReportProps>;
export type Reports = FeatureCollection<PointGeom, ReportProps>;
export type ReportCreate = { type: ReportType; comment?: string; lat: number; lon: number; source?: "form" | "coolpath" };

export type Recommendation = { shades: number; fountains: number; ac_repairs: number; priority: "high" | "medium" | "low"; text: string };
export type DistrictRating = {
  id: number;
  name: string;
  shade_deficit_index: number;
  index_components: DistrictProps["index_components"];
  open_reports: number;
  open_by_type: Record<ReportType, number>;
  cooling_points: number;
  cooling_density_km2: number;
  green_ratio: number;
  recommendation: Recommendation;
};
export type AdminSummary = {
  kpi: {
    open_reports: number;
    avg_deficit_index: number;
    reports_7d: number;
    reports_prev_7d: number;
    top_districts: { id: number; name: string; shade_deficit_index: number; open_reports: number }[];
  };
  districts: DistrictRating[];
  daily: { date: string; count: number }[];
  by_type: { type: ReportType; count: number }[];
  generated_at: string;
};

export type Districts = FeatureCollection<PolygonGeom, DistrictProps>;
export type CoolingPoints = FeatureCollection<PointGeom, CoolingPointProps>;
export type CoolingPoint = Feature<PointGeom, CoolingPointProps>;
export type HeatPoint = [number, number, number];
export type LatLon = [number, number];

export type RestStop = { id: number; name: string; type: CoolingType; lat: number; lon: number; at_m: number };
export type RouteOption = {
  id: number;
  label: string;
  kind: "shortest" | "alternative" | "via_cooling";
  source: "osrm" | "straight";
  geometry: { type: "LineString"; coordinates: [number, number][] };
  distance_m: number;
  duration_min: number;
  heat_exposure: number;
  shade_share_pct: number;
  heat_load: number;
  rest_stops: RestStop[];
  hottest_point: { lat: number; lon: number; district_name: string | null } | null;
  recommended: boolean;
};
export type CoolRoute = {
  routes: RouteOption[];
  recommended_id: number;
  comparison: { heat_less_pct: number; extra_min: number; text: string };
  heat_factor: number;
  feels_like: number | null;
  weather_source: string;
};

// ── Запросы ──────────────────────────────────────────────────────────────────
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RequestOpts = {
  params?: Record<string, string | number | undefined>;
  body?: unknown;
  method?: "GET" | "POST" | "PATCH";
  token?: string;
  raw?: boolean;
};

async function request<T>(path: string, { params, body, method, token, raw }: RequestOpts = {}): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  Object.entries(params ?? {}).forEach(([k, v]) => v !== undefined && url.searchParams.set(k, String(v)));
  let res: Response;
  try {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["X-Admin-Token"] = token; // токен живёт только в памяти React
    res = await fetch(url, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Сервер недоступен. Проверьте подключение к интернету.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : `Ошибка сервера (${res.status})`);
  }
  return (raw ? res : res.json()) as Promise<T>;
}

const getJson = <T,>(path: string, params?: Record<string, string | number | undefined>) => request<T>(path, { params });

export const api = {
  weather: (scenario?: "heatwave") => getJson<Weather>("/api/weather", { scenario }),
  districts: () => getJson<Districts>("/api/districts"),
  coolingPoints: () => getJson<CoolingPoints>("/api/cooling-points"),
  nearest: (lat: number, lon: number, limit = 5) =>
    getJson<CoolingPoints>("/api/cooling-points/nearest", { lat, lon, limit }),
  heatmap: (days = 30) => getJson<HeatPoint[]>("/api/reports/heatmap", { days }),
  reports: (fromIso?: string) => getJson<Reports>("/api/reports", { from: fromIso, limit: 1000 }),
  report: (id: number) => getJson<Report>(`/api/reports/${id}`),
  createReport: (body: ReportCreate) => request<Report>("/api/reports", { body }),
  // ── Панель акимата (заголовок X-Admin-Token) ──
  adminCheck: (token: string) => request<{ ok: boolean }>("/api/admin/check", { token }),
  adminSummary: (token: string) => request<AdminSummary>("/api/admin/summary", { token }),
  adminReports: (token: string) => request<Reports>("/api/reports", { token, params: { limit: 2000 } }),
  changeStatus: (token: string, id: number, status: ReportStatus, note?: string) =>
    request<Report>(`/api/reports/${id}/status`, { token, method: "PATCH", body: { status, note } }),
  demoReset: (token: string) =>
    request<{ removed_user_reports: number; demo_reports: number }>("/api/admin/demo/reset", { token, method: "POST", body: {} }),
  exportCsv: (token: string, params: Record<string, string | number | undefined>) =>
    request<Response>("/api/admin/reports.csv", { token, params, raw: true }),
  coolRoute: (from: LatLon, to: LatLon, scenario?: "heatwave") =>
    request<CoolRoute>("/api/route/cool", { body: { from, to, scenario } }),
};
