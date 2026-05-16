import { Outlet } from "react-router-dom";
import TabNav from "./components/TabNav";
import HealthBadge from "./components/HealthBadge";
import Toast from "./components/Toast";

export default function App() {
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "var(--sp-6)" }}>
      <header className="row" style={{ justifyContent: "space-between", marginBottom: "var(--sp-6)" }}>
        <h1 style={{ fontSize: "var(--fz-xl)", margin: 0 }}>TradingAgents</h1>
        <HealthBadge />
      </header>
      <TabNav />
      <main style={{ marginTop: "var(--sp-6)" }}>
        <Outlet />
      </main>
      <Toast />
    </div>
  );
}
