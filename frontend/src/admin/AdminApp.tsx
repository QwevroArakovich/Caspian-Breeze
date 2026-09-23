import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AdminSummary, type Districts, type Report, type ReportStatus, type Reports } from "../api";
import Toast from "../components/Toast";
import { formatDateTime } from "../lib/format";
import { REPORT_STATUSES } from "../lib/meta";
import AdminMap from "./AdminMap";
import Charts from "./Charts";
import DistrictRanking from "./DistrictRanking";
import Kpis from "./Kpis";
import Login from "./Login";
import { OPEN, type Filters } from "./filters";
import ReportsTable from "./ReportsTable";

const REFRESH_MS = 30 * 1000;

export default function AdminApp() {
  // Токен — только в памяти React: закрыли вкладку — нужно войти заново
  const [token, setToken] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [districts, setDistricts] = useState<Districts | null>(null);
  const [reports, setReports] = useState<Reports | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ statuses: OPEN, districtId: null, type: "", q: "" });
  const [toast, setToast] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const hideToast = useCallback(() => setToast(null), []);

  const logout = useCallback((reason?: string) => {
    setToken(null);
    setSummary(null);
    setReports(null);
    setLoginError(reason ?? null);
  }, []);

  const load = useCallback(
    async (t: string) => {
      try {
        const [s, d, r] = await Promise.all([api.adminSummary(t), api.districts(), api.adminReports(t)]);
        setSummary(s);
        setDistricts(d);
        setReports(r);
        setLoadError(null);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) logout("Токен больше не действует — войдите заново.");
        else setLoadError(e instanceof ApiError ? e.message : "Не удалось обновить данные");
      }
    },
    [logout],
  );

  useEffect(() => {
    if (!token) return;
    load(token);
    const t = window.setInterval(() => document.visibilityState === "visible" && load(token), REFRESH_MS);
    return () => window.clearInterval(t);
  }, [token, load]);

  const login = async (t: string) => {
    setChecking(true);
    setLoginError(null);
    try {
      await api.adminCheck(t);
      setToken(t);
    } catch (e) {
      setLoginError(e instanceof ApiError && e.status === 401 ? "Неверный токен." : "Сервер недоступен — попробуйте позже.");
    } finally {
      setChecking(false);
    }
  };

  const changeStatus = async (r: Report, status: ReportStatus, note: string) => {
    if (!token) return;
    try {
      const updated = await api.changeStatus(token, r.id, status, note.trim() || undefined);
      setReports((fc) => (fc ? { ...fc, features: fc.features.map((x) => (x.id === r.id ? { ...updated, properties: { ...updated.properties, history: null } } : x)) } : fc));
      setToast(`Заявка №${r.id}: «${REPORT_STATUSES[status].label}». Житель увидит это в «Моих заявках».`);
      load(token); // индекс и рейтинг пересчитаются
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Не удалось сохранить статус");
      throw e;
    }
  };

  const exportCsv = async () => {
    if (!token) return;
    setExporting(true);
    try {
      const res = await api.exportCsv(token, {
        status: filters.statuses.join(",") || undefined,
        district_id: filters.districtId ?? undefined,
        type: filters.type || undefined,
      });
      const blob = await res.blob();
      const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "caspian_breeze_reports.csv";
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Не удалось выгрузить CSV");
    } finally {
      setExporting(false);
    }
  };

  const demoReset = async () => {
    if (!token) return;
    const ok = window.confirm(
      "Демо-режим: удалить ВСЕ заявки (включая созданные на показе) и вернуть 42 демо-заявки со свежими датами?\n\nИспользуйте перед повторным прогоном питча.",
    );
    if (!ok) return;
    setResetting(true);
    try {
      const r = await api.demoReset(token);
      setFilters({ statuses: OPEN, districtId: null, type: "", q: "" });
      await load(token);
      setToast(`Демо-данные восстановлены: удалено заявок жителей — ${r.removed_user_reports}, демо-заявок — ${r.demo_reports}.`);
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Не удалось сбросить демо-данные");
    } finally {
      setResetting(false);
    }
  };

  if (!token) return <Login checking={checking} error={loginError} onLogin={login} />;

  const selectDistrict = (id: number | null) => setFilters((f) => ({ ...f, districtId: id }));

  return (
    <div className="min-h-dvh bg-cream">
      <header className="sticky top-0 z-[1100] border-b border-line bg-butter/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
          <h1 className="text-lg font-extrabold">
            🏛️ Caspian Breeze <span className="font-semibold text-muted">· диспетчер акимата Актау</span>
          </h1>
          <p className="text-xs text-muted">
            {summary ? `Обновлено ${formatDateTime(summary.generated_at)} · автообновление каждые 30 с` : "Загружаем данные…"}
          </p>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <a href="/" className="font-semibold text-sea underline underline-offset-2">Карта жителя</a>
            <button
              onClick={demoReset}
              disabled={resetting}
              title="Для повторных прогонов питча: вернуть данные к исходному состоянию"
              className="rounded-lg border border-sun-deep bg-sun px-3 py-1.5 font-semibold hover:bg-sun-deep hover:text-white disabled:opacity-50"
            >
              {resetting ? "Сбрасываем…" : "🔄 Демо-режим"}
            </button>
            <button onClick={() => logout()} className="rounded-lg border border-line bg-cream px-3 py-1.5 font-semibold hover:bg-sand">
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex max-w-[1400px] flex-col gap-4 px-4 py-4">
        {loadError && <p role="alert" className="rounded-xl bg-[#C8412B] px-3 py-2 text-sm text-white">{loadError}</p>}
        {summary && <Kpis kpi={summary.kpi} />}

        <div className="grid gap-4 lg:grid-cols-[7fr_5fr]">
          <AdminMap districts={districts} reports={reports} selectedId={filters.districtId} onSelect={selectDistrict} />
          <div className="min-h-0 lg:h-[442px]">
            {summary && <DistrictRanking districts={summary.districts} selectedId={filters.districtId} onSelect={selectDistrict} />}
          </div>
        </div>

        {summary && <Charts summary={summary} />}

        <ReportsTable
          reports={reports}
          districts={summary?.districts ?? []}
          filters={filters}
          onFilters={setFilters}
          onChangeStatus={changeStatus}
          onExport={exportCsv}
          exporting={exporting}
        />
      </main>

      {toast && (
        <div className="fixed inset-x-0 bottom-4 z-[1200] flex justify-center px-3">
          <Toast text={toast} onDone={hideToast} />
        </div>
      )}
    </div>
  );
}
