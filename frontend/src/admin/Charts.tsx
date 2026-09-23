import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AdminSummary } from "../api";
import { REPORT_TYPES } from "../lib/meta";

const TYPE_COLORS: Record<string, string> = { no_shade: "#E8822E", need_fountain: "#23868A", broken_ac: "#2E7FB8", other: "#9A9486" };

export default function Charts({ summary }: { summary: AdminSummary }) {
  const daily = summary.daily.map((d) => ({ ...d, label: `${d.date.slice(8, 10)}.${d.date.slice(5, 7)}` }));
  const types = summary.by_type.map((t) => ({ ...t, label: REPORT_TYPES[t.type].label }));
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr]">
      <section className="rounded-2xl border border-line bg-white/70 p-4">
        <h2 className="text-lg font-bold">Заявки по дням</h2>
        <p className="text-xs text-muted">последние 30 дней, время Актау</p>
        <div className="mt-2 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={daily} margin={{ left: -20, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="#EFDFA2" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#85764A" }} interval={4} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#85764A" }} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v: number) => [v, "заявок"]} labelFormatter={(l) => `Дата: ${l}`} cursor={{ fill: "#FFF3C7" }} />
              <Bar dataKey="count" fill="#D9A521" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="rounded-2xl border border-line bg-white/70 p-4">
        <h2 className="text-lg font-bold">На что жалуются</h2>
        <p className="text-xs text-muted">типы заявок за 30 дней</p>
        {types.length === 0 && <p className="mt-6 text-sm text-muted">За 30 дней жалоб не было — график появится с первой заявкой.</p>}
        <div className={`mt-2 h-56 ${types.length === 0 ? "hidden" : ""}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={types} layout="vertical" margin={{ left: 8, right: 24, top: 8 }}>
              <XAxis type="number" allowDecimals={false} hide />
              <YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 12, fill: "#43360F" }} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v: number) => [v, "заявок"]} cursor={{ fill: "#FFF3C7" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} label={{ position: "right", fontSize: 12, fill: "#43360F" }}>
                {types.map((t) => (
                  <Cell key={t.type} fill={TYPE_COLORS[t.type]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
