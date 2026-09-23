import type { CoolRoute, CoolingPoint, LatLon } from "../api";
import { formatDistance } from "../lib/format";
import { POINT_TYPES, routeColors } from "../lib/meta";

export type RouteEnd = { latlon: LatLon; label: string };
export type PickTarget = "from" | "to" | null;

type Props = {
  from: RouteEnd | null;
  to: RouteEnd | null;
  picking: PickTarget;
  presets: CoolingPoint[];
  status: "idle" | "locating" | "loading" | "error";
  error: string | null;
  result: CoolRoute | null;
  selectedId: number | null;
  onPick: (target: PickTarget) => void;
  onUseMyLocation: () => void;
  onPreset: (p: CoolingPoint) => void;
  onBuild: () => void;
  onSelectRoute: (id: number) => void;
  onReportHotspot: () => void;
  onClose: () => void;
};

function EndRow(props: {
  title: string;
  value: RouteEnd | null;
  active: boolean;
  onPickMap: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl border px-3 py-2 ${props.active ? "border-sea bg-sea-soft" : "border-line bg-white/60"}`}>
      <div className="flex items-center gap-2">
        <span className="w-12 shrink-0 text-xs font-semibold text-muted">{props.title}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">
          {props.active ? "Нажмите на карту…" : props.value?.label ?? "не выбрано"}
        </span>
        <button onClick={props.onPickMap} className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-sea hover:bg-sand">
          На карте
        </button>
      </div>
      {props.children}
    </div>
  );
}

export default function RoutePanel(p: Props) {
  const colors = p.result ? routeColors(p.result.routes) : {};
  const selected = p.result?.routes.find((r) => r.id === p.selectedId) ?? null;
  const sorted = p.result ? [...p.result.routes].sort((a, b) => a.heat_exposure - b.heat_exposure) : [];
  const approximate = p.result?.routes.some((r) => r.source === "straight");

  return (
    <section
      aria-label="Прохладный маршрут"
      aria-live="polite"
      className="max-h-[52vh] overflow-y-auto rounded-t-2xl border border-line bg-cream p-4 shadow-[0_-6px_24px_rgb(67_54_15/0.12)] md:max-h-[78vh] md:rounded-2xl"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-bold">Прохладный маршрут</h2>
        <button onClick={p.onClose} className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-sand" aria-label="Закрыть">
          ✕
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <EndRow title="Откуда" value={p.from} active={p.picking === "from"} onPickMap={() => p.onPick("from")}>
          {!p.from && (
            <button onClick={p.onUseMyLocation} className="mt-1 text-xs font-semibold text-sea underline underline-offset-2">
              {p.status === "locating" ? "Определяем…" : "📍 Моё местоположение"}
            </button>
          )}
        </EndRow>
        <EndRow title="Куда" value={p.to} active={p.picking === "to"} onPickMap={() => p.onPick("to")}>
          {p.presets.length > 0 && !p.result && (
            <div className="mt-1 flex flex-wrap gap-1">
              {p.presets.map((pt) => (
                <button
                  key={pt.id}
                  onClick={() => p.onPreset(pt)}
                  className="rounded-full border border-line bg-cream px-2 py-0.5 text-xs hover:bg-sand"
                >
                  {POINT_TYPES[pt.properties.type].emoji} {pt.properties.name}
                </button>
              ))}
            </div>
          )}
        </EndRow>
      </div>

      {!p.result && (
      <button
        onClick={p.onBuild}
        disabled={!p.from || !p.to || p.status === "loading"}
        className="mt-3 w-full rounded-xl bg-sea px-4 py-3 font-bold text-white hover:bg-[#1B6E71] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {p.status === "loading" ? "Сравниваем варианты…" : "Построить маршрут"}
      </button>
      )}
      {p.error && <p role="alert" className="mt-2 text-sm text-[#C8412B]">{p.error}</p>}

      {p.result && (
        <div className="mt-4">
          <div className="rounded-xl bg-sea-soft px-4 py-3 text-[#1D5557]">
            <p className="text-lg font-extrabold leading-tight">{p.result.comparison.text}</p>
            <p className="mt-0.5 text-xs">
              по сравнению с кратчайшим путём · жара учтена с коэффициентом {p.result.heat_factor.toFixed(2).replace(".", ",")}
            </p>
          </div>

          <ul className="mt-3 flex flex-col gap-2">
            {sorted.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => p.onSelectRoute(r.id)}
                  aria-pressed={r.id === p.selectedId}
                  className={`flex w-full items-start gap-3 rounded-xl border px-3 py-2 text-left ${
                    r.id === p.selectedId ? "border-ink/40 bg-white" : "border-line bg-white/60 hover:bg-sand"
                  }`}
                >
                  <span className="mt-1 h-3 w-8 shrink-0 rounded-full" style={{ background: colors[r.id] }} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">
                      {r.recommended && <span className="text-[#2F9E61]">Рекомендуем · </span>}
                      {r.label}
                    </span>
                    <span className="block text-xs text-muted">
                      {formatDistance(r.distance_m)} · {Math.round(r.duration_min)} мин · солнце {Math.round(r.heat_exposure)}/100 ·
                      в тени {Math.round(r.shade_share_pct)} %
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {selected && (
            <div className="mt-3 text-sm">
              {selected.rest_stops.length > 0 ? (
                <>
                  <p className="font-semibold">Где передохнуть по пути</p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {selected.rest_stops.map((s) => (
                      <li key={s.id} className="rounded-full bg-sand px-2 py-0.5 text-xs">
                        {POINT_TYPES[s.type].emoji} {s.name} · {formatDistance(s.at_m)}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-muted">На этом варианте нет точек отдыха в 100 м от пути.</p>
              )}
              {selected.hottest_point && (
                <div className="mt-3 rounded-xl border border-[#E8B4A8] bg-[#FBEAE5] px-3 py-2">
                  <p className="text-sm">
                    Самый открытый участок — {selected.hottest_point.district_name ?? "вне микрорайонов"} (красный круг на карте).
                  </p>
                  <button
                    onClick={p.onReportHotspot}
                    className="mt-2 rounded-lg bg-[#C8412B] px-3 py-1.5 text-sm font-bold text-white hover:bg-[#A8331F]"
                  >
                    📣 Здесь нет тени
                  </button>
                </div>
              )}
            </div>
          )}

          {approximate && (
            <p className="mt-3 text-xs text-muted">
              Сервис пешеходных маршрутов не ответил — линии показаны по прямой, расстояние оценено с запасом 25 %.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
