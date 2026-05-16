import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/analysis", label: "分析" },
  { to: "/history", label: "历史" },
  { to: "/config", label: "配置" },
  { to: "/diagnostics", label: "诊断" },
];

export default function TabNav() {
  return (
    <nav className="row" style={{ borderBottom: "1px solid var(--c-border)", gap: 0 }}>
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to}
          style={({ isActive }) => ({
            padding: "var(--sp-3) var(--sp-4)",
            color: isActive ? "var(--c-accent)" : "var(--c-text-dim)",
            borderBottom: isActive ? "2px solid var(--c-accent)" : "2px solid transparent",
            textDecoration: "none", fontWeight: 600,
          })}>
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
