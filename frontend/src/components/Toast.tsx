import { useEffect } from "react";
import { useAppStore } from "../store/appStore";

export default function Toast() {
  const toasts = useAppStore((s) => s.toasts);
  const dismiss = useAppStore((s) => s.dismissToast);
  useEffect(() => {
    if (toasts.length === 0) return;
    const id = toasts[toasts.length - 1].id;
    const t = setTimeout(() => dismiss(id), 4000);
    return () => clearTimeout(t);
  }, [toasts, dismiss]);
  return (
    <div style={{ position: "fixed", bottom: 16, right: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      {toasts.map((t) => (
        <div key={t.id} className="card"
          style={{ borderLeft: `4px solid ${t.kind === "ok" ? "var(--c-ok)" : "var(--c-err)"}` }}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
