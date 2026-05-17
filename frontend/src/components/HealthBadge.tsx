import { useEffect, useState } from "react";
import { getHealth } from "../api/client";

export default function HealthBadge() {
  const [ok, setOk] = useState<boolean | null>(null);
  const [model, setModel] = useState<string>("");
  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth()
        .then((h) => {
          if (!alive) return;
          setOk(true);
          setModel([h.model, h.provider && `· ${h.provider}`].filter(Boolean).join(" "));
        })
        .catch(() => alive && setOk(false));
    check();
    const id = setInterval(check, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return (
    <span
      className="col"
      style={{ gap: 2, alignItems: "flex-end", color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}
    >
      <span className="row" style={{ gap: "var(--sp-2)" }}>
        <span data-testid="health-dot" className={`dot ${ok ? "dot-ok" : "dot-err"}`} />
        {ok === null ? "检查中" : ok ? "后端在线" : "后端离线"}
      </span>
      {ok && model && <span data-testid="health-model">{model}</span>}
    </span>
  );
}
