import { useEffect, useState } from "react";
import { ApiError, api, type Report } from "../api";
import { formatDateTime } from "../lib/format";
import { REPORT_STATUSES, REPORT_TYPES } from "../lib/meta";

type Props = {
  initialId: number | null;
  recentIds: number[];
  refreshKey: number; // меняется при каждом опросе сервера — статус подтягивается сам
  onShowOnMap: (r: Report) => void;
  onClose: () => void;
};

export default function MyReportsPanel({ initialId, recentIds, refreshKey, onShowOnMap, onClose }: Props) {
  const [input, setInput] = useState(initialId ? String(initialId) : "");
  const [id, setId] = useState<number | null>(initialId);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0); // «Найти» по тому же номеру тоже перезагружает статус

  useEffect(() => {
    if (id === null) return;
    let cancelled = false;
    setLoading(true);
    api
      .report(id)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setReport(null);
        setError(e instanceof ApiError && e.status === 404 ? `Заявка №${id} не найдена. Проверьте номер.` : "Не удалось загрузить заявку.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, refreshKey, nonce]);

  const lookup = (value: string) => {
    const n = Number.parseInt(value, 10);
    if (Number.isFinite(n) && n > 0) {
      setInput(String(n));
      setId(n);
      setNonce((x) => x + 1);
    } else {
      setError("Введите номер заявки — только цифры.");
    }
  };

  const status = report ? REPORT_STATUSES[report.properties.status] : null;

  return (
    <section
      aria-label="Мои заявки"
      className="max-h-[60vh] overflow-y-auto rounded-t-2xl border border-line bg-cream p-4 shadow-[0_-6px_24px_rgb(67_54_15/0.12)] md:max-h-[78vh] md:rounded-2xl"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-bold">Мои заявки</h2>
        <button onClick={onClose} className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-sand" aria-label="Закрыть">
          ✕
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          lookup(input);
        }}
        className="flex gap-2"
      >
        <label className="sr-only" htmlFor="report-id">Номер заявки</label>
        <input
          id="report-id"
          inputMode="numeric"
          value={input}
          onChange={(e) => setInput(e.target.value.replace(/\D/g, ""))}
          placeholder="Номер заявки, например 42"
          className="min-w-0 flex-1 rounded-xl border border-line bg-white/80 px-3 py-2 outline-none focus:border-sea"
        />
        <button type="submit" className="rounded-xl bg-sea px-4 py-2 font-bold text-white hover:bg-[#1B6E71]">
          Найти
        </button>
      </form>

      {recentIds.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
          <span className="text-muted">Отправлены сейчас:</span>
          {recentIds.map((n) => (
            <button key={n} onClick={() => lookup(String(n))} className="rounded-full bg-sand px-2 py-0.5 font-semibold hover:bg-butter">
              №{n}
            </button>
          ))}
        </div>
      )}

      {error && <p role="alert" className="mt-3 text-sm text-[#C8412B]">{error}</p>}
      {loading && !report && <p className="mt-3 text-sm text-muted">Загружаем…</p>}

      {report && status && (
        <div className="mt-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-muted">Заявка №{report.id}</p>
              <p className="font-bold">
                {REPORT_TYPES[report.properties.type].emoji} {REPORT_TYPES[report.properties.type].label}
              </p>
              <p className="text-sm text-muted">{report.properties.district_name ?? "район уточняется"}</p>
            </div>
            <span className="shrink-0 rounded-full px-3 py-1 text-sm font-bold text-white" style={{ background: status.color }}>
              {status.label}
            </span>
          </div>
          {report.properties.comment && <p className="mt-2 rounded-xl bg-white/70 px-3 py-2 text-sm">{report.properties.comment}</p>}

          <h3 className="mt-4 text-sm font-semibold">История</h3>
          <ol className="mt-2 border-l-2 border-line pl-4">
            {(report.properties.history ?? []).map((h, i) => (
              <li key={i} className="relative mb-3 last:mb-0">
                <span
                  className="absolute -left-[23px] top-1 h-3 w-3 rounded-full border-2 border-cream"
                  style={{ background: REPORT_STATUSES[h.new_status].color }}
                />
                <p className="text-sm font-semibold">{REPORT_STATUSES[h.new_status].label}</p>
                <p className="text-xs text-muted">
                  {formatDateTime(h.changed_at)}
                  {h.note ? ` · ${h.note}` : ""}
                </p>
              </li>
            ))}
          </ol>
          <button onClick={() => onShowOnMap(report)} className="mt-3 text-sm font-semibold text-sea underline underline-offset-2">
            Показать на карте
          </button>
        </div>
      )}
    </section>
  );
}
