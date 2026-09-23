import { useMemo, useState } from "react";
import type { DistrictRating } from "../api";
import { indexColor, indexTextColor } from "../lib/meta";

type SortKey = "shade_deficit_index" | "open_reports" | "cooling_density_km2" | "name";
const PRIORITY = { high: { label: "высокий", color: "#C8412B" }, medium: { label: "средний", color: "#E8922E" }, low: { label: "низкий", color: "#7FB069" } };

type Props = { districts: DistrictRating[]; selectedId: number | null; onSelect: (id: number | null) => void };

export default function DistrictRanking({ districts, selectedId, onSelect }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "shade_deficit_index", desc: true });
  const rows = useMemo(() => {
    const k = sort.key;
    return [...districts].sort((a, b) => {
      const v = k === "name" ? a.name.localeCompare(b.name, "ru", { numeric: true }) : (a[k] as number) - (b[k] as number);
      return sort.desc ? -v : v;
    });
  }, [districts, sort]);

  const Th = ({ k, children, className = "" }: { k: SortKey; children: React.ReactNode; className?: string }) => (
    <th className={`px-2 py-2 font-semibold ${className}`} aria-sort={sort.key === k ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button onClick={() => setSort((s) => ({ key: k, desc: s.key === k ? !s.desc : k !== "name" }))} className="hover:text-sea">
        {children} {sort.key === k ? (sort.desc ? "↓" : "↑") : ""}
      </button>
    </th>
  );

  return (
    <section className="flex h-full max-h-[480px] min-h-0 flex-col rounded-2xl border border-line bg-white/70 lg:max-h-none">
      <div className="flex items-baseline justify-between px-4 pt-3">
        <h2 className="text-lg font-bold">Рейтинг микрорайонов</h2>
        {selectedId !== null && (
          <button onClick={() => onSelect(null)} className="text-xs font-semibold text-sea underline underline-offset-2">
            Сбросить выбор
          </button>
        )}
      </div>
      <p className="px-4 text-xs text-muted">Нажмите на строку — заявки ниже отфильтруются по микрорайону.</p>
      <div className="mt-2 min-h-0 flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-sand text-left text-xs text-muted">
            <tr>
              <Th k="name">Мкр</Th>
              <Th k="shade_deficit_index">Индекс</Th>
              <Th k="open_reports">Заявки</Th>
              <Th k="cooling_density_km2" className="hidden xl:table-cell">Укрытий/км²</Th>
              <th className="px-2 py-2 font-semibold">Что сделать</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => {
              const pr = PRIORITY[d.recommendation.priority];
              return (
                <tr
                  key={d.id}
                  onClick={() => onSelect(d.id === selectedId ? null : d.id)}
                  className={`cursor-pointer border-t border-line align-top ${d.id === selectedId ? "bg-sea-soft" : "hover:bg-sand/60"}`}
                >
                  <td className="whitespace-nowrap px-2 py-2 font-semibold">{d.name}</td>
                  <td className="px-2 py-2">
                    <span className="rounded-md px-1.5 py-0.5 text-xs font-bold" style={{ background: indexColor(d.shade_deficit_index), color: indexTextColor(d.shade_deficit_index) }}>
                      {d.shade_deficit_index.toFixed(1).replace(".", ",")}
                    </span>
                  </td>
                  <td className="px-2 py-2 tabular-nums">{d.open_reports}</td>
                  <td className="hidden px-2 py-2 tabular-nums xl:table-cell">{d.cooling_density_km2.toFixed(1).replace(".", ",")}</td>
                  <td className="px-2 py-2">
                    <span className="block leading-snug">{d.recommendation.text}</span>
                    <span className="text-[11px] font-semibold" style={{ color: pr.color }}>
                      приоритет: {pr.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
