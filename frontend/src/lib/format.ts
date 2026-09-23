import type { HourlyWeather } from "../api";

const WALK_M_PER_MIN = 75; // 4,5 км/ч
const STREET_FACTOR = 1.2; // по улицам длиннее, чем по прямой

export function walkMinutes(distanceM: number): number {
  return Math.max(1, Math.round((distanceM * STREET_FACTOR) / WALK_M_PER_MIN));
}

export function formatDistance(m: number): string {
  return m < 1000 ? `${Math.round(m / 10) * 10} м` : `${(m / 1000).toFixed(1).replace(".", ",")} км`;
}

const hourOf = (iso: string) => iso.slice(11, 16);

/**
 * Совет по часам: первый непрерывный отрезок прогноза, когда ощущаемая температура ≥ 32 °C.
 * «С 12:00 до 16:00 избегайте открытых участков». null — если опасных часов нет.
 */
export function hotWindowAdvice(hourly: HourlyWeather[], threshold = 32): string | null {
  const start = hourly.findIndex((h) => h.feels_like >= threshold);
  if (start === -1) return null;
  let end = start;
  while (end + 1 < hourly.length && hourly[end + 1].feels_like >= threshold) end++;
  const from = hourOf(hourly[start].time);
  const toIso = hourly[end + 1]?.time;
  const to = toIso ? hourOf(toIso) : null;
  return to
    ? `С ${from} до ${to} избегайте открытых участков.`
    : `С ${from} и до вечера избегайте открытых участков.`;
}

// Грубая проверка «пользователь в Актау»: ~20 км от центра
export function isNearAktau(lat: number, lon: number): boolean {
  const dLat = (lat - 43.658) * 111;
  const dLon = (lon - 51.172) * 111 * Math.cos((43.658 * Math.PI) / 180);
  return Math.hypot(dLat, dLon) < 20;
}

const DATE_FMT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Aqtau" });
export const formatDateTime = (iso: string) => DATE_FMT.format(new Date(iso));

/** ISO-строка «N дней назад» для фильтра ?from= */
export const daysAgoIso = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();
