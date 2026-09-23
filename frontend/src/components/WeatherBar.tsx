import type { Weather } from "../api";
import { hotWindowAdvice } from "../lib/format";
import { HEAT_LEVELS } from "../lib/meta";
import type { HeatLevel } from "../api";

function levelOf(feels: number): HeatLevel {
  if (feels < 27) return "normal";
  if (feels < 32) return "caution";
  if (feels < 39) return "danger";
  return "extreme";
}

type Props = {
  weather: Weather | null;
  error: string | null;
  compact?: boolean;
  demo?: boolean;
  forced?: boolean; // реальная погода недоступна — симуляция включена автоматически
  onToggleDemo?: (on: boolean) => void;
};

export default function WeatherBar({ weather, error, compact = false, demo = false, forced = false, onToggleDemo }: Props) {
  if (error && !weather) {
    return (
      <section className="rounded-2xl border border-line bg-cream/95 px-4 py-3 text-sm shadow-sm backdrop-blur">
        Погода временно недоступна: {error}
      </section>
    );
  }
  if (!weather) {
    return (
      <section aria-busy="true" className="h-[92px] animate-pulse rounded-2xl border border-line bg-cream/90 shadow-sm" />
    );
  }

  const level = HEAT_LEVELS[weather.heat_level];
  const advice = hotWindowAdvice(weather.hourly) ?? weather.advice;

  return (
    <section
      aria-label="Погода в Актау"
      className="overflow-hidden rounded-2xl border border-line bg-cream/95 shadow-sm backdrop-blur"
    >
      <div className="flex items-stretch">
        {/* Главная цифра — ощущаемая температура на цвете уровня опасности */}
        <div
          className="flex min-w-[96px] flex-col justify-center px-4 py-2"
          style={{ background: level.color, color: level.text }}
        >
          <span className="text-[11px] font-medium opacity-90">ощущается</span>
          <span className="text-[40px] font-extrabold leading-none tracking-tight">
            {Math.round(weather.feels_like)}°
          </span>
          <span className="mt-1 text-xs font-semibold">{level.label}</span>
        </div>

        <div className="min-w-0 flex-1 px-3 py-2">
          <p className="text-xs text-muted">
            Термометр {Math.round(weather.temperature)}° · UV {Math.round(weather.uv_index)} · ветер{" "}
            {Math.round(weather.wind_speed)} км/ч
          </p>
          <p className={`mt-1 font-medium leading-snug ${compact ? "line-clamp-2 text-[13px]" : "text-sm"}`}>{advice}</p>
        </div>
      </div>

      {/* Лента прогноза: цвет каждого часа — уровень жары */}
      {!compact && (
      <div className="flex gap-px bg-line" aria-label="Прогноз ощущаемой температуры на 12 часов">
        {weather.hourly.map((h, i) => {
          const c = HEAT_LEVELS[levelOf(h.feels_like)];
          return (
            <div
              key={h.time}
              title={`${h.time.slice(11, 16)} — ощущается ${Math.round(h.feels_like)}°`}
              className="flex flex-1 flex-col items-center py-1 text-[10px] font-semibold"
              style={{ background: c.color, color: c.text }}
            >
              <span>{Math.round(h.feels_like)}°</span>
              <span className="opacity-80">{i % 3 === 0 ? h.time.slice(11, 13) : "\u00a0"}</span>
            </div>
          );
        })}
      </div>
      )}

      {!compact && (
        <div className="flex items-center gap-2 bg-sand px-3 py-1.5 text-[11px] text-muted">
          <span className="min-w-0 flex-1">
            {weather.source === "simulation"
              ? forced
                ? "СИМУЛЯЦИЯ: реальная погода недоступна — показан типичный июльский день."
                : "СИМУЛЯЦИЯ: типичный июльский день в Актау, +41 °C. Маршруты считаются для этой жары."
              : weather.stale
                ? "Последние сохранённые данные: Open-Meteo сейчас не отвечает."
                : "Реальная погода Актау сейчас (Open-Meteo)."}
          </span>
          {onToggleDemo && !forced && (
            <label className="flex shrink-0 cursor-pointer items-center gap-1.5 font-semibold text-ink">
              <input
                type="checkbox"
                role="switch"
                checked={demo}
                onChange={(e) => onToggleDemo(e.target.checked)}
                className="h-4 w-4 accent-[#C8412B]"
              />
              +41 °C, июль
            </label>
          )}
        </div>
      )}
    </section>
  );
}
