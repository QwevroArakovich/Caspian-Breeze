import { useState } from "react";
import type { LatLon, Report, ReportType } from "../api";
import { REPORT_TYPES } from "../lib/meta";

export type ReportDraft = {
  type: ReportType;
  comment: string;
  point: { latlon: LatLon; label: string } | null;
  source: "form" | "coolpath";
};

type Props = {
  draft: ReportDraft;
  picking: boolean;
  locating: boolean;
  sending: boolean;
  error: string | null;
  created: Report | null;
  fromRoute: boolean;
  onChange: (d: ReportDraft) => void;
  onPickOnMap: () => void;
  onUseMyLocation: () => void;
  onSubmit: () => void;
  onShowStatus: (id: number) => void;
  onNewReport: () => void;
  onBackToRoute: () => void;
  onClose: () => void;
};

const MAX_COMMENT = 500;

export default function ReportPanel(p: Props) {
  const [copied, setCopied] = useState(false);
  const d = p.draft;

  if (p.created) {
    const r = p.created;
    const link = `${window.location.origin}${window.location.pathname}?report=${r.id}`;
    return (
      <section aria-live="polite" className="rounded-t-2xl border border-line bg-cream p-4 shadow-[0_-6px_24px_rgb(67_54_15/0.12)] md:rounded-2xl">
        <p className="text-3xl" aria-hidden>✅</p>
        <h2 className="mt-1 text-xl font-extrabold">Заявка №{r.id} принята</h2>
        <p className="mt-1 text-sm">
          {REPORT_TYPES[r.properties.type].label} · {r.properties.district_name ?? "район уточняется"}. Диспетчер акимата
          увидит её сразу, а вы — каждое изменение статуса.
        </p>
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-sand px-3 py-2 text-xs">
          <span className="min-w-0 flex-1 truncate">{link}</span>
          <button
            onClick={() => navigator.clipboard?.writeText(link).then(() => setCopied(true))}
            className="shrink-0 font-semibold text-sea"
          >
            {copied ? "Скопировано" : "Копировать ссылку"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => p.onShowStatus(r.id)} className="rounded-xl bg-sea px-4 py-2.5 font-bold text-white hover:bg-[#1B6E71]">
            Следить за статусом
          </button>
          {p.fromRoute ? (
            <button onClick={p.onBackToRoute} className="rounded-xl border border-line px-4 py-2.5 font-semibold hover:bg-sand">
              Вернуться к маршруту
            </button>
          ) : (
            <button onClick={p.onNewReport} className="rounded-xl border border-line px-4 py-2.5 font-semibold hover:bg-sand">
              Ещё одна заявка
            </button>
          )}
          <button onClick={p.onClose} className="rounded-xl px-3 py-2.5 text-sm text-muted hover:bg-sand">
            Закрыть
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label="Сообщить о проблеме"
      className="max-h-[60vh] overflow-y-auto rounded-t-2xl border border-line bg-cream p-4 shadow-[0_-6px_24px_rgb(67_54_15/0.12)] md:max-h-[78vh] md:rounded-2xl"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-bold">Сообщить о проблеме</h2>
        <button onClick={p.onClose} className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-sand" aria-label="Закрыть">
          ✕
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          p.onSubmit();
        }}
        className="flex flex-col gap-3"
      >
        <fieldset>
          <legend className="mb-1 text-xs font-semibold text-muted">Что не так</legend>
          <div className="grid grid-cols-2 gap-2">
            {(Object.keys(REPORT_TYPES) as ReportType[]).map((t) => (
              <label
                key={t}
                className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-sea ${
                  d.type === t ? "border-sea bg-sea-soft font-semibold" : "border-line bg-white/60 hover:bg-sand"
                }`}
              >
                <input
                  type="radio"
                  name="report-type"
                  value={t}
                  checked={d.type === t}
                  onChange={() => p.onChange({ ...d, type: t })}
                  className="sr-only"
                />
                <span aria-hidden>{REPORT_TYPES[t].emoji}</span>
                <span className="leading-tight">{REPORT_TYPES[t].label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <p className="mb-1 text-xs font-semibold text-muted">Где</p>
          <div className={`rounded-xl border px-3 py-2 ${p.picking ? "border-sea bg-sea-soft" : "border-line bg-white/60"}`}>
            <p className="text-sm font-semibold">
              {p.picking ? "Нажмите на карту…" : p.locating ? "Определяем, где вы…" : d.point?.label ?? "Место не выбрано"}
            </p>
            <div className="mt-1 flex gap-3 text-xs font-semibold text-sea">
              <button type="button" onClick={p.onUseMyLocation} className="underline underline-offset-2">
                📍 Моё местоположение
              </button>
              <button type="button" onClick={p.onPickOnMap} className="underline underline-offset-2">
                Указать на карте
              </button>
            </div>
          </div>
        </div>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-muted">Комментарий (необязательно)</span>
          <textarea
            value={d.comment}
            maxLength={MAX_COMMENT}
            rows={3}
            onChange={(e) => p.onChange({ ...d, comment: e.target.value })}
            placeholder="Например: у школы нет ни одного навеса, дети ждут на солнце"
            className="w-full resize-none rounded-xl border border-line bg-white/80 px-3 py-2 text-sm outline-none focus:border-sea"
          />
          <span className="block text-right text-[11px] text-muted">
            {d.comment.length}/{MAX_COMMENT}
          </span>
        </label>

        {p.error && <p role="alert" className="text-sm text-[#C8412B]">{p.error}</p>}

        <button
          type="submit"
          disabled={!d.point || p.sending}
          className="w-full rounded-xl bg-sea px-4 py-3 font-bold text-white hover:bg-[#1B6E71] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {p.sending ? "Отправляем…" : "Отправить заявку"}
        </button>
        <p className="text-[11px] text-muted">
          Без регистрации. Заявку увидит диспетчер акимата; статус можно проверить по номеру.
        </p>
      </form>
    </section>
  );
}
