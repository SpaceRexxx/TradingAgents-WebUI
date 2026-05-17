import type { ReactNode } from "react";

export interface Metric {
  label: string;
  value: string | number;
}

export function fmtInt(n: number): string {
  return Math.round(n || 0).toLocaleString("en-US");
}

export function fmtCost(n: number): string {
  return n && n > 0 ? `$${n.toFixed(4)}` : "—";
}

export default function StatCard({
  title,
  metrics,
  footer,
}: {
  title: string;
  metrics: Metric[];
  footer?: ReactNode;
}) {
  return (
    <div className="card col" style={{ gap: "var(--sp-4)" }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div className="row" style={{ flexWrap: "wrap", gap: "var(--sp-6)" }}>
        {metrics.map((m) => (
          <div key={m.label} className="col" style={{ gap: 2, minWidth: 120 }}>
            <span style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
              {m.label}
            </span>
            <span style={{ fontSize: "var(--fz-xl)", fontWeight: 700 }}>{m.value}</span>
          </div>
        ))}
      </div>
      {footer && (
        <div style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>{footer}</div>
      )}
    </div>
  );
}
