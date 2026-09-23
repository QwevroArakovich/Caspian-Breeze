import type { CoolingPoint } from "../api";
import { formatDistance, walkMinutes } from "../lib/format";
import { POINT_TYPES } from "../lib/meta";

export type NearestState =
  | { kind: "locating" }
  | { kind: "picking"; reason?: string }
  | { kind: "loading" }
  | { kind: "results"; points: CoolingPoint[]; fromGps: boolean }
  | { kind: "error"; message: string };

type Props = {
  state: NearestState;
  selectedId: number | null;
  onSelect: (p: CoolingPoint) => void;
  onPickOnMap: () => void;
  onRetryGps: () => void;
  onClose: () => void;
};

export default function NearestPanel({ state, selectedId, onSelect, onPickOnMap, onRetryGps, onClose }: Props) {
  return (
    <section
      aria-label="Ближайшая прохлада"
      aria-live="polite"
      className="max-h-[46vh] overflow-y-auto rounded-t-2xl border border-line bg-cream p-4 shadow-[0_-6px_24px_rgb(67_54_15/0.12)] md:max-h-[70vh] md:rounded-2xl"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-bold">Ближайшая прохлада</h2>
        <button onClick={onClose} className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-sand" aria-label="Закрыть">
          ✕
        </button>
      </div>

      {state.kind === "locating" && <p className="text-sm text-muted">Определяем, где вы…</p>}
      {state.kind === "loading" && <p className="text-sm text-muted">Ищем ближайшие точки…</p>}

      {state.kind === "picking" && (
        <div className="rounded-xl bg-sea-soft p-3 text-sm text-[#1D5557]">
          {state.reason && <p className="mb-1">{state.reason}</p>}
          <p className="font-semibold">Нажмите на карту там, где вы находитесь.</p>
        </div>
      )}

      {state.kind === "error" && (
        <div className="text-sm">
          <p className="mb-2">{state.message}</p>
          <button onClick={onRetryGps} className="rounded-xl bg-sun px-3 py-2 font-semibold hover:bg-sun-deep hover:text-white">
            Повторить
          </button>
        </div>
      )}

      {state.kind === "results" && state.points.length === 0 && (
        <p className="text-sm">
          Поблизости точек охлаждения не нашлось.{" "}
          <button onClick={onPickOnMap} className="font-semibold text-sea underline underline-offset-2">Указать другое место</button>
        </p>
      )}
      {state.kind === "results" && state.points.length > 0 && (
        <>
          <ol className="flex flex-col gap-2">
            {state.points.map((p) => {
              const meta = POINT_TYPES[p.properties.type];
              const d = p.properties.distance_m ?? 0;
              const active = p.id === selectedId;
              return (
                <li key={p.id}>
                  <button
                    onClick={() => onSelect(p)}
                    className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors ${
                      active ? "border-sea bg-sea-soft" : "border-line bg-white/60 hover:bg-sand"
                    }`}
                  >
                    <span className="text-2xl" aria-hidden>{meta.emoji}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{p.properties.name}</span>
                      <span className="block text-xs text-muted">
                        {meta.label}
                        {p.properties.hours ? ` · ${p.properties.hours}` : ""}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="block font-bold">{walkMinutes(d)} мин</span>
                      <span className="block text-xs text-muted">{formatDistance(d)}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-xs text-muted">
            {state.fromGps ? "По вашему местоположению. " : "От точки на карте. "}
            Время пешком — с поправкой на улицы.{" "}
            <button onClick={onPickOnMap} className="font-semibold text-sea underline underline-offset-2">
              Указать другое место
            </button>
          </p>
        </>
      )}
    </section>
  );
}
