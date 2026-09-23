import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CoolRoute,
  type CoolingPoint,
  type CoolingPoints,
  type Districts,
  type HeatPoint,
  type LatLon,
  type Report,
  type Reports,
  type Weather,
} from "./api";
import LayerPanel, { type Layers } from "./components/LayerPanel";
import MapView from "./components/MapView";
import NearestPanel, { type NearestState } from "./components/NearestPanel";
import MyReportsPanel from "./components/MyReportsPanel";
import ReportPanel, { type ReportDraft } from "./components/ReportPanel";
import RoutePanel, { type PickTarget, type RouteEnd } from "./components/RoutePanel";
import Toast from "./components/Toast";
import WeatherBar from "./components/WeatherBar";
import { daysAgoIso, isNearAktau } from "./lib/format";

// Сценарий берём из адреса (?scenario=heatwave), а не из localStorage
const QUERY = new URLSearchParams(window.location.search);
const SCENARIO = QUERY.get("scenario") === "heatwave" ? "heatwave" : undefined;
// ?report=42 — ссылка на заявку из уведомления «Заявка принята» (без регистрации)
const LINKED_REPORT = Number.parseInt(QUERY.get("report") ?? "", 10) || null;
const WEATHER_REFRESH_MS = 10 * 60 * 1000;
const DATA_REFRESH_MS = 30 * 1000; // опрос заявок: проще и надёжнее WebSocket
const EMPTY_DRAFT: ReportDraft = { type: "no_shade", comment: "", point: null, source: "form" };

const DEFAULT_LAYERS: Layers = { indoor: true, water: true, shade: true, breeze: true, districts: true, heatmap: false, reports: true };

// Быстрые пункты назначения для демо (ищутся по имени среди точек охлаждения)
const PRESET_NAMES = ["Набережная Актау · 1 мкр", "ТРЦ Aktau City Mall", "Сквер у памятника Т. Шевченко"];

const message = (e: unknown) => (e instanceof ApiError ? e.message : "Не удалось загрузить данные");

export default function App() {
  const [weather, setWeather] = useState<Weather | null>(null);
  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [districts, setDistricts] = useState<Districts | null>(null);
  const [points, setPoints] = useState<CoolingPoints | null>(null);
  const [heat, setHeat] = useState<HeatPoint[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [heatwave, setHeatwave] = useState(SCENARIO === "heatwave");
  const [weatherForced, setWeatherForced] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);

  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS);
  const [layersOpen, setLayersOpen] = useState(false);

  const [nearest, setNearest] = useState<NearestState | null>(null);
  const [me, setMe] = useState<[number, number] | null>(null);
  const [selected, setSelected] = useState<CoolingPoint | null>(null);

  // CoolPath
  const [routeOpen, setRouteOpen] = useState(false);
  const [routeFrom, setRouteFrom] = useState<RouteEnd | null>(null);
  const [routeTo, setRouteTo] = useState<RouteEnd | null>(null);
  const [pickTarget, setPickTarget] = useState<PickTarget>(null);
  const [routeStatus, setRouteStatus] = useState<"idle" | "locating" | "loading" | "error">("idle");
  const [routeError, setRouteError] = useState<string | null>(null);
  const [routeResult, setRouteResult] = useState<CoolRoute | null>(null);
  const [routeSelected, setRouteSelected] = useState<number | null>(null);

  // Заявки жителей
  const [reports, setReports] = useState<Reports | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportFromRoute, setReportFromRoute] = useState(false);
  const [draft, setDraft] = useState<ReportDraft>(EMPTY_DRAFT);
  const [reportPicking, setReportPicking] = useState(false);
  const [reportLocating, setReportLocating] = useState(false);
  const [reportSending, setReportSending] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [created, setCreated] = useState<Report | null>(null);
  const [myIds, setMyIds] = useState<number[]>([]);
  const [myOpen, setMyOpen] = useState(LINKED_REPORT !== null);
  const [myInitialId, setMyInitialId] = useState<number | null>(LINKED_REPORT);
  const [highlightId, setHighlightId] = useState<number | null>(LINKED_REPORT);
  const [focus, setFocus] = useState<LatLon | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const hideToast = useCallback(() => setToast(null), []);

  // Погода: переключатель «+41 °C, июль» (симуляция) или реальная погода Open-Meteo.
  // Если Open-Meteo недоступен (503) — симуляция включается сама и помечается как вынужденная.
  useEffect(() => {
    const load = () =>
      api
        .weather(heatwave ? "heatwave" : undefined)
        .then((w) => {
          setWeather(w);
          setWeatherForced(false);
          setWeatherError(null);
        })
        .catch((e) => {
          if (e instanceof ApiError && e.status === 503 && !heatwave) {
            return api.weather("heatwave").then((w) => {
              setWeather(w);
              setWeatherForced(true);
            });
          }
          setWeatherError(message(e));
        })
        .catch((e) => setWeatherError(message(e)));
    load();
    const t = window.setInterval(load, WEATHER_REFRESH_MS);
    return () => window.clearInterval(t);
  }, [heatwave]);

  const toggleHeatwave = (on: boolean) => {
    setHeatwave(on);
    // Состояние — в адресе, а не в localStorage: ссылку можно отправить, перезагрузка его сохранит
    const url = new URL(window.location.href);
    if (on) url.searchParams.set("scenario", "heatwave");
    else url.searchParams.delete("scenario");
    window.history.replaceState(null, "", url);
    resetRouteResult();
  };

  // Статические слои: районы и точки. Ошибка — баннер с кнопкой «Повторить»
  const loadStatic = useCallback(() => {
    setLoadError(null);
    Promise.all([api.districts().then(setDistricts), api.coolingPoints().then(setPoints)]).catch((e) =>
      setLoadError(message(e)),
    );
  }, []);
  useEffect(() => loadStatic(), [loadStatic]);

  // Нет сети — показываем плашку и продолжаем работать с тем, что уже загружено
  useEffect(() => {
    const on = () => {
      setOnline(true);
      loadStatic();
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [loadStatic]);

  // Заявки, тепловая карта и индекс районов обновляются каждые 30 с: новые жалобы и статусы видны без перезагрузки
  const refreshLive = useCallback(() => {
    api.reports(daysAgoIso(30)).then(setReports).catch(() => undefined);
    api.heatmap().then(setHeat).catch(() => setHeat((h) => h ?? []));
    api.districts().then(setDistricts).catch(() => undefined);
    setRefreshTick((t) => t + 1);
  }, []);

  useEffect(() => {
    refreshLive();
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshLive();
    }, DATA_REFRESH_MS);
    return () => window.clearInterval(t);
  }, [refreshLive]);

  const findNearest = useCallback(async (lat: number, lon: number, fromGps: boolean) => {
    setMe([lat, lon]);
    setSelected(null);
    setNearest({ kind: "loading" });
    try {
      const fc = await api.nearest(lat, lon, 5);
      setNearest({ kind: "results", points: fc.features, fromGps });
    } catch (e) {
      setNearest({ kind: "error", message: message(e) });
    }
  }, []);

  const startNearest = useCallback(() => {
    setLayersOpen(false);
    setRouteOpen(false);
    setReportOpen(false);
    setMyOpen(false);
    if (!("geolocation" in navigator)) {
      setNearest({ kind: "picking", reason: "Браузер не умеет определять местоположение." });
      return;
    }
    setNearest({ kind: "locating" });
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (isNearAktau(coords.latitude, coords.longitude)) {
          findNearest(coords.latitude, coords.longitude, true);
        } else {
          setNearest({ kind: "picking", reason: "Похоже, вы сейчас не в Актау." });
        }
      },
      () => setNearest({ kind: "picking", reason: "Доступ к геолокации не получен." }),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
    );
  }, [findNearest]);

  const closeNearest = () => {
    setNearest(null);
    setMe(null);
    setSelected(null);
  };

  // ── CoolPath ──
  const resetRouteResult = () => {
    setRouteResult(null);
    setRouteSelected(null);
    setRouteError(null);
  };

  const openRoute = () => {
    closeNearest();
    setLayersOpen(false);
    setReportOpen(false);
    setMyOpen(false);
    setRouteOpen(true);
    if (!routeFrom) setPickTarget("from");
  };

  const closeRoute = () => {
    setRouteOpen(false);
    setPickTarget(null);
    resetRouteResult();
    setRouteFrom(null);
    setRouteTo(null);
    setRouteStatus("idle");
  };

  const setEnd = (target: "from" | "to", end: RouteEnd) => {
    resetRouteResult();
    if (target === "from") {
      setRouteFrom(end);
      setPickTarget(routeTo ? null : "to");
    } else {
      setRouteTo(end);
      setPickTarget(routeFrom ? null : "from");
    }
  };

  const useMyLocationAsStart = () => {
    if (!("geolocation" in navigator)) {
      setRouteError("Браузер не умеет определять местоположение — выберите старт на карте.");
      setPickTarget("from");
      return;
    }
    setRouteStatus("locating");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setRouteStatus("idle");
        if (isNearAktau(coords.latitude, coords.longitude)) {
          setEnd("from", { latlon: [coords.latitude, coords.longitude], label: "Моё местоположение" });
        } else {
          setRouteError("Похоже, вы сейчас не в Актау — выберите старт на карте.");
          setPickTarget("from");
        }
      },
      () => {
        setRouteStatus("idle");
        setRouteError("Доступ к геолокации не получен — выберите старт на карте.");
        setPickTarget("from");
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
    );
  };

  const buildRoute = async () => {
    if (!routeFrom || !routeTo) return;
    setPickTarget(null);
    setRouteStatus("loading");
    setRouteError(null);
    try {
      const scenario = heatwave || weather?.source === "simulation" ? "heatwave" : undefined;
      const res = await api.coolRoute(routeFrom.latlon, routeTo.latlon, scenario);
      setRouteResult(res);
      setRouteSelected(res.recommended_id);
      setRouteStatus("idle");
    } catch (e) {
      setRouteStatus("error");
      setRouteError(message(e));
    }
  };

  const presets = useMemo(
    () =>
      PRESET_NAMES.map((n) => points?.features.find((p) => p.properties.name === n)).filter(
        (p): p is CoolingPoint => Boolean(p),
      ),
    [points],
  );

  // ── Заявки ──
  const locateForReport = () => {
    setReportError(null);
    setReportPicking(false);
    if (!("geolocation" in navigator)) {
      setReportPicking(true);
      return;
    }
    setReportLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setReportLocating(false);
        if (isNearAktau(coords.latitude, coords.longitude)) {
          setDraft((d) => ({ ...d, point: { latlon: [coords.latitude, coords.longitude], label: "Моё местоположение" } }));
        } else {
          setReportError("Похоже, вы сейчас не в Актау — укажите место на карте.");
          setReportPicking(true);
        }
      },
      () => {
        setReportLocating(false);
        setReportError("Доступ к геолокации не получен — укажите место на карте.");
        setReportPicking(true);
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
    );
  };

  /** Обычная заявка: по умолчанию — моё местоположение */
  const openReport = () => {
    closeNearest();
    setLayersOpen(false);
    setMyOpen(false);
    if (routeOpen) closeRoute();
    setCreated(null);
    setReportFromRoute(false);
    setDraft(EMPTY_DRAFT);
    setReportOpen(true);
    locateForReport();
  };

  /** Из маршрута: «Здесь нет тени» на самом открытом участке — точка уже заполнена */
  const reportHotspot = () => {
    const r = routeResult?.routes.find((x) => x.id === routeSelected);
    if (!r?.hottest_point) return;
    const hp = r.hottest_point;
    setCreated(null);
    setReportError(null);
    setReportPicking(false);
    setReportFromRoute(true);
    setDraft({
      type: "no_shade",
      comment: `Маршрут «${routeFrom?.label ?? "старт"} → ${routeTo?.label ?? "финиш"}»: открытый участок без тени`,
      point: { latlon: [hp.lat, hp.lon], label: `Участок маршрута · ${hp.district_name ?? "вне микрорайонов"}` },
      source: "coolpath",
    });
    setReportOpen(true);
  };

  const closeReport = () => {
    setReportOpen(false);
    setReportPicking(false);
    setCreated(null);
    if (!reportFromRoute) setDraft(EMPTY_DRAFT);
  };

  const submitReport = async () => {
    if (!draft.point) return;
    setReportSending(true);
    setReportError(null);
    try {
      const r = await api.createReport({
        type: draft.type,
        comment: draft.comment.trim() || undefined,
        lat: draft.point.latlon[0],
        lon: draft.point.latlon[1],
        source: draft.source,
      });
      setCreated(r);
      setMyIds((ids) => [r.id, ...ids.filter((x) => x !== r.id)]);
      setHighlightId(r.id);
      setFocus([r.geometry.coordinates[1], r.geometry.coordinates[0]]);
      setReports((fc) => (fc ? { ...fc, features: [r, ...fc.features] } : fc)); // маркер сразу, не ждём опроса
      setToast(`Заявка №${r.id} принята, район: ${r.properties.district_name ?? "уточняется"}`);
      setDraft(EMPTY_DRAFT);
      refreshLive();
    } catch (e) {
      setReportError(message(e));
    } finally {
      setReportSending(false);
    }
  };

  const openMyReports = (id: number | null) => {
    closeNearest();
    setLayersOpen(false);
    setReportOpen(false);
    if (routeOpen) closeRoute();
    setMyInitialId(id);
    if (id) setHighlightId(id);
    setMyOpen(true);
  };

  const showReportOnMap = (r: Report) => {
    setHighlightId(r.id);
    setFocus([r.geometry.coordinates[1], r.geometry.coordinates[0]]);
  };

  const onMapPick = (lat: number, lon: number) => {
    if (reportOpen && reportPicking) {
      setDraft((d) => ({ ...d, point: { latlon: [lat, lon], label: "Точка на карте" } }));
      setReportPicking(false);
    } else if (routeOpen && pickTarget) {
      setEnd(pickTarget, { latlon: [lat, lon] as LatLon, label: "Точка на карте" });
    } else if (nearest?.kind === "picking") {
      findNearest(lat, lon, false);
    }
  };

  const nearestIds = useMemo(
    () => new Set(nearest?.kind === "results" ? nearest.points.map((p) => p.id) : []),
    [nearest],
  );

  return (
    <div className="relative h-dvh w-full overflow-hidden">
      <MapView
        layers={layers}
        districts={districts}
        points={points}
        heat={heat}
        picking={nearest?.kind === "picking" || (reportOpen && reportPicking) || (!reportOpen && routeOpen && pickTarget !== null)}
        onMapPick={onMapPick}
        me={me}
        nearestIds={nearestIds}
        selected={selected}
        route={
          routeOpen
            ? { from: routeFrom?.latlon ?? null, to: routeTo?.latlon ?? null, result: routeResult, selectedId: routeSelected }
            : null
        }
        reports={reports}
        highlightReportId={highlightId}
        reportPoint={reportOpen && !created ? draft.point?.latlon ?? null : null}
        focus={focus}
        onHotspotClick={reportHotspot}
      />

      {/* Верх: погода + кнопка слоёв */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex items-start gap-2 p-3 pt-[max(12px,env(safe-area-inset-top))]">
        <div className="pointer-events-auto min-w-0 flex-1 md:max-w-[440px]">
          <h1 className="sr-only">Caspian Breeze — карта прохлады Актау</h1>
          <WeatherBar weather={weather} error={weatherError} compact={nearest !== null || routeOpen || reportOpen || myOpen} demo={heatwave}
            forced={weatherForced}
            onToggleDemo={toggleHeatwave}
          />
          {!online && (
            <p role="status" className="mt-2 rounded-xl bg-ink px-3 py-2 text-sm text-cream">
              Нет подключения к интернету — показываем последние загруженные данные.
            </p>
          )}
          {loadError && online && (
            <div role="alert" className="mt-2 flex items-center gap-2 rounded-xl bg-[#C8412B] px-3 py-2 text-sm text-white">
              <span className="min-w-0 flex-1">{loadError}</span>
              <button onClick={loadStatic} className="shrink-0 rounded-lg bg-white/20 px-2 py-1 font-semibold hover:bg-white/30">
                Повторить
              </button>
            </div>
          )}
        </div>
        <div className="pointer-events-auto relative md:ml-auto">
          <button
            onClick={() => setLayersOpen((v) => !v)}
            aria-expanded={layersOpen}
            className="grid h-12 w-12 place-items-center rounded-2xl border border-line bg-cream text-xl shadow-sm hover:bg-sand"
            aria-label="Слои карты"
            title="Слои карты"
          >
            🗂️
          </button>
          <button
            onClick={() => openMyReports(myIds[0] ?? null)}
            className="mt-2 grid h-12 w-12 place-items-center rounded-2xl border border-line bg-cream text-xl shadow-sm hover:bg-sand"
            aria-label="Мои заявки"
            title="Мои заявки"
          >
            🧾
          </button>
          {layersOpen && (
            <div className="absolute right-0 top-14">
              <LayerPanel layers={layers} onChange={setLayers} onClose={() => setLayersOpen(false)} />
            </div>
          )}
        </div>
      </header>

      {toast && (
        <div className="pointer-events-none absolute inset-x-0 top-[max(12px,env(safe-area-inset-top))] z-[1100] flex justify-center px-3">
          <Toast text={toast} onDone={hideToast} />
        </div>
      )}

      {/* Низ: панель режима или главные кнопки */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1000] md:bottom-4 md:left-4 md:right-auto md:w-[400px]">
        {nearest ? (
          <div className="pointer-events-auto">
            <NearestPanel
              state={nearest}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
              onPickOnMap={() => setNearest({ kind: "picking" })}
              onRetryGps={startNearest}
              onClose={closeNearest}
            />
          </div>
        ) : reportOpen ? (
          <div className="pointer-events-auto">
            <ReportPanel
              draft={draft}
              picking={reportPicking}
              locating={reportLocating}
              sending={reportSending}
              error={reportError}
              created={created}
              fromRoute={reportFromRoute}
              onChange={setDraft}
              onPickOnMap={() => setReportPicking(true)}
              onUseMyLocation={locateForReport}
              onSubmit={submitReport}
              onShowStatus={(id) => openMyReports(id)}
              onNewReport={openReport}
              onBackToRoute={() => {
                setReportOpen(false);
                setCreated(null);
              }}
              onClose={closeReport}
            />
          </div>
        ) : myOpen ? (
          <div className="pointer-events-auto">
            <MyReportsPanel
              key={myInitialId ?? "none"}
              initialId={myInitialId}
              recentIds={myIds}
              refreshKey={refreshTick}
              onShowOnMap={showReportOnMap}
              onClose={() => setMyOpen(false)}
            />
          </div>
        ) : routeOpen ? (
          <div className="pointer-events-auto">
            <RoutePanel
              from={routeFrom}
              to={routeTo}
              picking={pickTarget}
              presets={presets}
              status={routeStatus}
              error={routeError}
              result={routeResult}
              selectedId={routeSelected}
              onPick={setPickTarget}
              onUseMyLocation={useMyLocationAsStart}
              onPreset={(pt) =>
                setEnd("to", {
                  latlon: [pt.geometry.coordinates[1], pt.geometry.coordinates[0]],
                  label: pt.properties.name,
                })
              }
              onBuild={buildRoute}
              onSelectRoute={setRouteSelected}
              onReportHotspot={reportHotspot}
              onClose={closeRoute}
            />
          </div>
        ) : (
          <div className="flex justify-center gap-1.5 p-3 pb-[max(14px,env(safe-area-inset-bottom))] md:justify-start md:gap-2 md:p-0">
            <button
              onClick={startNearest}
              className="pointer-events-auto whitespace-nowrap rounded-full bg-sea px-3.5 py-3.5 text-[14px] font-bold text-white shadow-lg hover:bg-[#1B6E71] md:px-4 md:text-[15px]"
            >
              🌊 <span className="md:hidden">Прохлада рядом</span>
              <span className="hidden md:inline">Ближайшая прохлада</span>
            </button>
            <button
              onClick={openRoute}
              className="pointer-events-auto whitespace-nowrap rounded-full border border-sun-deep bg-sun px-3.5 py-3.5 text-[14px] font-bold text-ink shadow-lg hover:bg-sun-deep hover:text-white md:px-4 md:text-[15px]"
            >
              🧭 Маршрут в тени
            </button>
            <button
              onClick={openReport}
              aria-label="Сообщить о проблеме"
              title="Сообщить о проблеме"
              className="pointer-events-auto flex h-[50px] w-[50px] shrink-0 items-center justify-center gap-1 rounded-full border border-line bg-cream text-xl shadow-lg hover:bg-sand md:w-auto md:px-4 md:text-[15px] md:font-bold"
            >
              <span aria-hidden>📣</span>
              <span className="hidden md:inline"> Сообщить о проблеме</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
