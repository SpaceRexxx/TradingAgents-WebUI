import { useEffect, useState } from "react";
import { getDiagnostics, runDiagnostics } from "../api/client";
import type { DiagnosticsResponse } from "../api/types";
import { useAppStore } from "../store/appStore";

export default function DiagnosticsPage() {
  const [data, setData] = useState<DiagnosticsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const pushToast = useAppStore((s) => s.pushToast);

  const load = (fn: () => Promise<DiagnosticsResponse>) => {
    setBusy(true);
    fn().then(setData).catch((e) => pushToast("err", `诊断失败: ${e.status ?? e}`)).finally(() => setBusy(false));
  };
  useEffect(() => { load(getDiagnostics); }, []);

  return (
    <div className="col">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>数据源诊断</h2>
        <button className="btn" disabled={busy} onClick={() => load(runDiagnostics)}>重新检测</button>
      </div>
      {data && data.degraded.length === 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--c-ok)" }}>全部数据源正常</div>
      )}
      {data && data.degraded.map((d, i) => (
        <div key={i} className="card" style={{ borderLeft: "4px solid var(--c-warn)" }}>{d}</div>
      ))}
      {data && <div style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>检测时间: {data.checked_at}</div>}
    </div>
  );
}
