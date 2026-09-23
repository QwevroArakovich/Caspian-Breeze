import type { CoolingType, HeatLevel, ReportStatus, ReportType } from "../api";

export const AKTAU_CENTER: [number, number] = [43.658, 51.172];
export const AKTAU_ZOOM = 13;

// Группы слоёв на карте и тип точки → группа
export type PointGroup = "indoor" | "water" | "shade" | "breeze";
export const GROUPS: Record<PointGroup, { label: string; emoji: string }> = {
  indoor: { label: "Прохладные помещения", emoji: "❄️" },
  water: { label: "Питьевая вода", emoji: "💧" },
  shade: { label: "Тенистые зоны", emoji: "🌳" },
  breeze: { label: "Набережная и бриз", emoji: "🌊" },
};

export const POINT_TYPES: Record<CoolingType, { label: string; emoji: string; group: PointGroup }> = {
  ac_bus_stop: { label: "Остановка с кондиционером", emoji: "❄️", group: "indoor" },
  mall: { label: "Торговый центр", emoji: "🛍️", group: "indoor" },
  library: { label: "Библиотека", emoji: "📚", group: "indoor" },
  fountain: { label: "Питьевой фонтанчик", emoji: "💧", group: "water" },
  pharmacy: { label: "Аптека: вода и первая помощь", emoji: "⚕️", group: "water" },
  park: { label: "Парк, сквер, аллея", emoji: "🌳", group: "shade" },
  embankment: { label: "Набережная, морской бриз", emoji: "🌊", group: "breeze" },
};

export const HEAT_LEVELS: Record<HeatLevel, { label: string; color: string; text: string }> = {
  normal: { label: "Комфортно", color: "#7FB069", text: "#fff" },
  caution: { label: "Осторожно", color: "#E9B949", text: "#43360F" },
  danger: { label: "Опасно", color: "#E8822E", text: "#fff" },
  extreme: { label: "Экстремальная жара", color: "#C8412B", text: "#fff" },
};

// Шкала индекса дефицита тени (та же, что в Streamlit-демо)
export const INDEX_SCALE: { max: number; color: string; label: string }[] = [
  { max: 35, color: "#F3DC7B", label: "до 35" },
  { max: 50, color: "#F2B443", label: "35–50" },
  { max: 65, color: "#EB8A2F", label: "50–65" },
  { max: 80, color: "#DB5A2B", label: "65–80" },
  { max: Infinity, color: "#B3342A", label: "80+" },
];

export const indexColor = (v: number) => INDEX_SCALE.find((s) => v < s.max)!.color;
/** Цвет текста поверх indexColor: на тёмно-красных — белый, чтобы читалось */
export const indexTextColor = (v: number) => (v >= 65 ? "#fff" : "#43360F");

// Цвета вариантов маршрута: рекомендованный — зелёный, остальные — тёплые
const OTHER_ROUTE_COLORS = ["#D9A521", "#8C7B4F", "#C8412B"];
export const RECOMMENDED_COLOR = "#2F9E61";
export function routeColors(routes: { id: number; recommended: boolean }[]): Record<number, string> {
  let k = 0;
  return Object.fromEntries(
    routes.map((r) => [r.id, r.recommended ? RECOMMENDED_COLOR : OTHER_ROUTE_COLORS[k++ % OTHER_ROUTE_COLORS.length]]),
  );
}

export const REPORT_TYPES: Record<ReportType, { label: string; emoji: string }> = {
  no_shade: { label: "Нет тени или навеса", emoji: "☀️" },
  need_fountain: { label: "Нужна питьевая вода", emoji: "💧" },
  broken_ac: { label: "Не работает кондиционер на остановке", emoji: "❄️" },
  other: { label: "Другое", emoji: "✏️" },
};

export const REPORT_STATUSES: Record<ReportStatus, { label: string; color: string }> = {
  new: { label: "Новая", color: "#D64933" },
  in_review: { label: "На рассмотрении", color: "#E8922E" },
  planned: { label: "Запланировано", color: "#2E7FB8" },
  done: { label: "Выполнено", color: "#3F9143" },
  rejected: { label: "Отклонено", color: "#9A9486" },
};
