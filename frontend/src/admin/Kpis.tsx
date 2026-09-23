import type { AdminSummary } from "../api";
import { indexColor, indexTextColor } from "../lib/meta";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-white/70 px-4 py-3">
      <h2 className="text-sm text-muted">{title}</h2>
      {children}
    </section>
  );
}

export default function Kpis({ kpi }: { kpi: AdminSummary["kpi"] }) {
  const diff = kpi.reports_7d - kpi.reports_prev_7d;
  const pct = kpi.reports_prev_7d ? Math.round((diff / kpi.reports_prev_7d) * 100) : null;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Card title="Открытые заявки">
        <p className="text-4xl font-extrabold">{kpi.open_reports}</p>
        <p className="text-xs text-muted">новые, на рассмотрении, запланированные</p>
      </Card>
      <Card title="Средний индекс нехватки тени">
        <p className="text-4xl font-extrabold">
          {kpi.avg_deficit_index.toFixed(1).replace(".", ",")}
          <span className="text-base font-semibold text-muted"> / 100</span>
        </p>
        <p className="text-xs text-muted">по всем микрорайонам</p>
      </Card>
      <Card title="Заявки за 7 дней">
        <p className="text-4xl font-extrabold">{kpi.reports_7d}</p>
        <p className={`text-xs font-semibold ${diff > 0 ? "text-[#C8412B]" : "text-[#3F9143]"}`}>
          {pct === null ? "нет данных за прошлую неделю" : `${diff >= 0 ? "+" : ""}${pct} % к прошлой неделе (${kpi.reports_prev_7d})`}
        </p>
      </Card>
      <Card title="Топ-3 проблемных микрорайона">
        <ol className="mt-1 flex flex-col gap-1">
          {kpi.top_districts.map((d, i) => (
            <li key={d.id} className="flex items-center gap-2 text-sm">
              <span className="w-4 text-muted">{i + 1}</span>
              <span className="flex-1 whitespace-nowrap font-semibold">{d.name}</span>
              <span className="rounded-md px-1.5 text-xs font-bold" style={{ background: indexColor(d.shade_deficit_index), color: indexTextColor(d.shade_deficit_index) }}>
                {Math.round(d.shade_deficit_index)}
              </span>
              <span className="w-16 text-right text-xs text-muted">{d.open_reports} заяв.</span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
