import { useState } from "react";

type Props = { checking: boolean; error: string | null; onLogin: (token: string) => void };

export default function Login({ checking, error, onLogin }: Props) {
  const [token, setToken] = useState("");
  return (
    <main className="grid min-h-dvh place-items-center bg-cream p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (token.trim()) onLogin(token.trim());
        }}
        className="w-full max-w-sm rounded-2xl border border-line bg-white/70 p-6 shadow-sm"
      >
        <p className="text-3xl" aria-hidden>🏛️</p>
        <h1 className="mt-2 text-2xl font-extrabold">Панель диспетчера</h1>
        <p className="mt-1 text-sm text-muted">Caspian Breeze · акимат г. Актау, отдел благоустройства</p>
        <label className="mt-5 block">
          <span className="mb-1 block text-sm font-semibold">Токен доступа</span>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="w-full rounded-xl border border-line bg-white px-3 py-2.5 outline-none focus:border-sea"
            placeholder="Выдаётся администратором"
          />
        </label>
        {error && <p role="alert" className="mt-2 text-sm text-[#C8412B]">{error}</p>}
        <button
          type="submit"
          disabled={checking || !token.trim()}
          className="mt-4 w-full rounded-xl bg-sea px-4 py-3 font-bold text-white hover:bg-[#1B6E71] disabled:opacity-50"
        >
          {checking ? "Проверяем…" : "Войти"}
        </button>
        <p className="mt-3 text-xs text-muted">Токен хранится только в этой вкладке и пропадёт после её закрытия.</p>
        <a href="/" className="mt-4 inline-block text-sm font-semibold text-sea underline underline-offset-2">
          ← Карта для жителей
        </a>
      </form>
    </main>
  );
}
