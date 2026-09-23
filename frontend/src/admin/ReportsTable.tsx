import { useMemo, useState } from "react";
import type { DistrictRating, Report, ReportStatus, ReportType, Reports } from "../api";
import { formatDateTime } from "../lib/format";
import { REPORT_STATUSES, REPORT_TYPES } from "../lib/meta";
import type { Filters } from "./filters";

const SOURCE = { seed: "демо", form: "форма", coolpath: "маршрут" } as const;
const PAGE = 50;

type Props = {
  reports: Reports | null;
  districts: DistrictRating[];
  filters: Filters;
  onFilters: (f: Filters) => void;
  onChangeStatus: (r: Report, status: ReportStatus, note: string) => Promise<void>;
  onExport: () => void;
  exporting: boolean;
};

function StatusEditor({ report, onSave }: { report: Report; onSave: (s: ReportStatus, note: string) => Promise<void> }) {
  const [status, setStatus] = useState<ReportStatus>(report.properties.status === "new" ? "in_review" : report.properties.status);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
          await onSave(status, note);
        } finally {
          setSaving(false);
        }
      }}
      className="flex flex-col gap-2 rounded-xl bg-sand/70 p-3"
    >
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Новый статус">
        {(Object.keys(REPORT_STATUSES) as ReportStatus[]).map((s) => (
          <button
            type="button"
            key={s}
            role="radio"
            aria-checked={status === s}
            onClick={() => setStatus(s)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${status === s ? "text-white" : "bg-white"}`}
            style={status === s ? { background: REPORT_STATUSES[s].color, borderColor: REPORT_STATUSES[s].color } : { borderColor: "#EFDFA2" }}
          >
            {REPORT_STATUSES[s].label}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          placeholder="Комментарий для жителя: например, «Навес включён в план на октябрь»"
          className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-sea"
        />
        <button type="submit" disabled={saving} className="rounded-lg bg-sea px-4 py-2 text-sm font-bold text-white hover:bg-[#1B6E71] disabled:opacity-50">
          {saving ? "Сохраняем…" : "Сохранить статус"}
        </button>
      </div>
      <p className="text-[11px] text-muted">Житель увидит новый статус и комментарий в «Моих заявках» в течение 30 секунд.</p>
    </form>
  );
}

export default function ReportsTable({ reports, districts, filters, onFilters, onChangeStatus, onExport, exporting }: Props) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE);

  const rows = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return (reports?.features ?? []).filter(
      (r) =>
        (filters.statuses.length === 0 || filters.statuses.includes(r.properties.status)) &&
        (filters.districtId === null || r.properties.district_id === filters.districtId) &&
        (!filters.type || r.properties.type === filters.type) &&
        (!q || (r.properties.comment ?? "").toLowerCase().includes(q) || String(r.id) === q),
    );
  }, [reports, filters]);

  const toggleStatus = (s: ReportStatus) =>
    onFilters({ ...filters, statuses: filters.statuses.includes(s) ? filters.statuses.filter((x) => x !== s) : [...filters.statuses, s] });

  return (
    <section className="rounded-2xl border border-line bg-white/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">
          Заявки <span className="text-base font-semibold text-muted">· {rows.length}</span>
        </h2>
        <button
          onClick={onExport}
          disabled={exporting}
          className="rounded-xl border border-sun-deep bg-sun px-4 py-2 text-sm font-bold hover:bg-sun-deep hover:text-white disabled:opacity-50"
        >
          {exporting ? "Готовим файл…" : "⬇ Экспорт CSV для благоустройства"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {(Object.keys(REPORT_STATUSES) as ReportStatus[]).map((s) => {
          const on = filters.statuses.includes(s);
          return (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              aria-pressed={on}
              className="flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold"
              style={{ borderColor: on ? REPORT_STATUSES[s].color : "#EFDFA2", background: on ? `${REPORT_STATUSES[s].color}1f` : "white" }}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: REPORT_STATUSES[s].color }} />
              {REPORT_STATUSES[s].label}
            </button>
          );
        })}
        <select
          value={filters.districtId ?? ""}
          onChange={(e) => onFilters({ ...filters, districtId: e.target.value ? Number(e.target.value) : null })}
          className="rounded-lg border border-line bg-white px-2 py-1 text-sm"
          aria-label="Микрорайон"
        >
          <option value="">Все микрорайоны</option>
          {[...districts].sort((a, b) => a.name.localeCompare(b.name, "ru", { numeric: true })).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select
          value={filters.type}
          onChange={(e) => onFilters({ ...filters, type: e.target.value as ReportType | "" })}
          className="rounded-lg border border-line bg-white px-2 py-1 text-sm"
          aria-label="Тип"
        >
          <option value="">Все типы</option>
          {(Object.keys(REPORT_TYPES) as ReportType[]).map((t) => (
            <option key={t} value={t}>
              {REPORT_TYPES[t].label}
            </option>
          ))}
        </select>
        <input
          value={filters.q}
          onChange={(e) => onFilters({ ...filters, q: e.target.value })}
          placeholder="Поиск по тексту или №"
          className="min-w-[160px] flex-1 rounded-lg border border-line bg-white px-3 py-1 text-sm outline-none focus:border-sea"
        />
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-sand text-left text-xs text-muted">
            <tr>
              <th className="px-2 py-2">№</th>
              <th className="px-2 py-2">Создана</th>
              <th className="px-2 py-2">Мкр</th>
              <th className="px-2 py-2">Тип</th>
              <th className="px-2 py-2">Комментарий</th>
              <th className="px-2 py-2">Источник</th>
              <th className="px-2 py-2">Статус</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((r) => {
              const st = REPORT_STATUSES[r.properties.status];
              const open = r.id === openId;
              return [
                <tr
                  key={r.id}
                  onClick={() => setOpenId(open ? null : r.id)}
                  className={`cursor-pointer border-t border-line align-top ${open ? "bg-sea-soft" : "hover:bg-sand/60"}`}
                >
                  <td className="px-2 py-2 font-semibold tabular-nums">{r.id}</td>
                  <td className="whitespace-nowrap px-2 py-2 text-xs">{formatDateTime(r.properties.created_at)}</td>
                  <td className="whitespace-nowrap px-2 py-2">{r.properties.district_name ?? "—"}</td>
                  <td className="px-2 py-2">
                    {REPORT_TYPES[r.properties.type].emoji} {REPORT_TYPES[r.properties.type].label}
                  </td>
                  <td className="max-w-[320px] px-2 py-2 text-xs text-muted">{r.properties.comment ?? "—"}</td>
                  <td className="px-2 py-2 text-xs">{SOURCE[r.properties.source]}</td>
                  <td className="px-2 py-2">
                    <span className="whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-bold text-white" style={{ background: st.color }}>
                      {st.label}
                    </span>
                  </td>
                </tr>,
                open && (
                  <tr key={`${r.id}-edit`} className="bg-sea-soft/50">
                    <td colSpan={7} className="px-2 pb-3">
                      <StatusEditor
                        report={r}
                        onSave={async (s, note) => {
                          await onChangeStatus(r, s, note);
                          setOpenId(null);
                        }}
                      />
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
        {rows.length === 0 && <p className="py-6 text-center text-sm text-muted">Нет заявок под эти фильтры — измените статус или микрорайон.</p>}
        {rows.length > limit && (
          <button onClick={() => setLimit((l) => l + PAGE)} className="mt-2 w-full rounded-lg py-2 text-sm font-semibold text-sea hover:bg-sand">
            Показать ещё {Math.min(PAGE, rows.length - limit)}
          </button>
        )}
      </div>
    </section>
  );
}
