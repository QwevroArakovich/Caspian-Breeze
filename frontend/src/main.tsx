import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// Панель акимата — отдельный маршрут /admin, грузится только диспетчеру (свой чанк с графиками)
const AdminApp = lazy(() => import("./admin/AdminApp.tsx"));
const isAdmin = window.location.pathname.replace(/\/+$/, "").endsWith("/admin");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isAdmin ? (
      <Suspense fallback={<p className="p-6 text-muted">Загрузка панели…</p>}>
        <AdminApp />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
