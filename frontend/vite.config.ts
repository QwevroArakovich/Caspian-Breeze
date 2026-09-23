import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  // Прод-сборка без адреса API молча ходила бы на localhost — лучше упасть сразу с понятной ошибкой
  if (command === "build" && mode === "production" && !env.VITE_API_URL) {
    throw new Error(
      "VITE_API_URL не задан. На Vercel: Settings → Environment Variables → VITE_API_URL = https://<ваш-backend>",
    );
  }
  return {
    plugins: [react(), tailwindcss()],
    server: { host: true, port: 5173 },
  };
});
