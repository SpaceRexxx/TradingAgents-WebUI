import { useEffect, useState } from "react";
import { getHealth } from "../api/client";

export default function HealthBadge() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth().then(() => alive && setOk(true)).catch(() => alive && setOk(false));
    check();
    const id = setInterval(check, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return (
    <span className="row" style={{ gap: "var(--sp-2)", color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
      <span data-testid="health-dot" className={`dot ${ok ? "dot-ok" : "dot-err"}`} />
      {ok === null ? "检查中" : ok ? "后端在线" : "后端离线"}
    </span>
  );
}
