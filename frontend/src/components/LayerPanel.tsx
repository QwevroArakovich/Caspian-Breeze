import { GROUPS, INDEX_SCALE, type PointGroup } from "../lib/meta";

export type Layers = { districts: boolean; heatmap: boolean; reports: boolean } & Record<PointGroup, boolean>;

type Props = { layers: Layers; onChange: (l: Layers) => void; onClose: () => void };

function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 hover:bg-sand">
      <input
        type="checkbox"
        className="h-5 w-5 accent-[#23868A]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-sm">{children}</span>
    </label>
  );
}

export default function LayerPanel({ layers, onChange, onClose }: Props) {
  const set = (k: keyof Layers) => (v: boolean) => onChange({ ...layers, [k]: v });
  return (
    <div
      role="dialog"
      aria-label="Слои карты"
      className="w-[min(300px,calc(100vw-24px))] rounded-2xl border border-line bg-cream p-3 shadow-lg"
    >
      <div className="mb-1 flex items-center justify-between px-2">
        <h2 className="text-base font-bold">Что показать</h2>
        <button onClick={onClose} className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-sand" aria-label="Закрыть">
          ✕
        </button>
      </div>

      <p className="px-2 pt-1 text-xs font-semibold text-muted">Где прохладно</p>
      {(Object.keys(GROUPS) as PointGroup[]).map((g) => (
        <Toggle key={g} checked={layers[g]} onChange={set(g)}>
          {GROUPS[g].emoji} {GROUPS[g].label}
        </Toggle>
      ))}

      <p className="px-2 pt-2 text-xs font-semibold text-muted">Где жарко</p>
      <Toggle checked={layers.districts} onChange={set("districts")}>
        Нехватка тени по микрорайонам
      </Toggle>
      {layers.districts && (
        <div className="mb-1 ml-10 flex overflow-hidden rounded-md text-[10px] font-semibold">
          {INDEX_SCALE.map((s) => (
            <span key={s.label} className="flex-1 py-0.5 text-center" style={{ background: s.color }}>
              {s.label}
            </span>
          ))}
        </div>
      )}
      <Toggle checked={layers.reports} onChange={set("reports")}>
        Заявки жителей (цвет — статус)
      </Toggle>
      <Toggle checked={layers.heatmap} onChange={set("heatmap")}>
        Тепловая карта жалоб
      </Toggle>
    </div>
  );
}
