import { useEffect } from "react";

export default function Toast({ text, onDone }: { text: string; onDone: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onDone, 5000);
    return () => window.clearTimeout(t);
  }, [text, onDone]);
  return (
    <div role="status" className="pointer-events-auto rounded-2xl bg-ink px-4 py-3 text-sm font-semibold text-cream shadow-lg">
      {text}
    </div>
  );
}
