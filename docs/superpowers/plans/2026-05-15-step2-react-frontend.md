# Step 2 — React + Vite Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `frontend/` Vite + React + TypeScript SPA that consumes the complete backend API (15 endpoints) — replacing Streamlit's role with a real client: 4 tabs (Analysis / History / Config / Diagnostics), WebSocket-driven live streaming, Markdown-rendered agent reports.

**Architecture:** Vite + React 18 + TypeScript SPA. A single typed API-client module mirrors every backend endpoint; a `useAnalysisStream` hook owns the WebSocket lifecycle; Zustand holds cross-component state; React Router gives each tab a deep-linkable route. Dev server proxies `/api` → `http://localhost:8765` (CORS for `:5173` is already configured in `backend/config.py`). Agent reports render via `react-markdown` + `remark-gfm`. Streamlit (`webapp.py`) is left running until Phase E's cutover, then de-referenced from docs/Docker (the file itself is deleted only after the user explicitly confirms).

**Tech Stack:** Vite 5, React 18, TypeScript 5, Zustand 4, react-router-dom 6, react-markdown 9 + remark-gfm 4, Vitest 2 + @testing-library/react 16 + jsdom. Native `fetch` + native `WebSocket` (no axios). Node ≥ 22 (v25 confirmed available).

**Scope boundary:** Frontend only. The backend (tagged `step-1a6-endpoints-complete`) is NOT modified. `cli/` is untouched and remains supported. `webapp.py` is NOT edited; it is retired (docs/Docker stop referencing it) in Phase E and physically deleted only on explicit user confirmation.

**No design mockup exists** (`design/index.html` from the original brief is absent from the repo). The UI uses a clean neutral token-based design system defined in Phase A — functional and professional, not pixel-matched. Visual polish is an explicit post-Step-2 follow-up.

**Rollback:** All work is additive under `frontend/`. `git reset --hard refs/tags/step-1a6-endpoints-complete` removes the entire frontend. Phase E's doc/Docker edits are the only changes outside `frontend/` and are called out per-file.

**Backend API contract (pinned — do not re-derive):**
- `GET /api/health` → `{"status":"ok"}`
- `POST /api/analysis/start` body `{ticker, trade_date, config_overrides}` → `{run_id}`
- `WS /api/analysis/ws/{run_id}` → JSON events: `{type:"status",status:"running"}` · `{type:"chunk",payload:{...nodeDeltaKeys}}` · `{type:"done",status:"done"}` · `{type:"aborted"}` · `{type:"error",message}` · `{type:"ping"}`
- `POST /api/analysis/{run_id}/abort` → `{run_id, accepted}` (404 if unknown)
- `GET /api/history?ticker=` → `{items:[{ticker,trade_date,rating,summary,model,provider,note,user_rating,created_at,json_path}]}`
- `PATCH /api/history/{ticker}/{trade_date}` body `{note?, rating?}` → `{ticker,trade_date,updated}` (404 if rating on a non-indexed run)
- `GET /api/history/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}` → `{a,b,sections:{key:{changed,diff}}}` (404 if either side missing)
- `GET /api/diagnostics` → `{degraded:string[], checked_at}`
- `POST /api/diagnostics/run` → same shape
- `GET /api/providers` → `{providers:[{id,name,env_var,base_url,configured}]}`
- `POST /api/providers/{id}/key` body `{api_key}` → `{id,configured}` (404 unknown, 400 keyless, 422 newline)
- `POST /api/providers/{id}/test` → `{id,ok,reason,status?}`
- `GET /api/runs/{ticker}/{trade_date}/pdf` → `application/pdf` bytes (404 if not indexed)

---

## File Structure

```
frontend/
├── package.json                # deps + scripts (dev/build/test)
├── vite.config.ts              # React plugin + /api + /ws proxy to :8765 + vitest config
├── tsconfig.json               # strict TS
├── index.html                  # Vite entry
├── .gitignore
├── src/
│   ├── main.tsx                # React root + Router
│   ├── App.tsx                 # layout shell: header + 4 tab nav + <Outlet/>
│   ├── test-setup.ts           # jest-dom matchers
│   ├── styles/{tokens.css, components.css}
│   ├── api/{types.ts, client.ts, client.test.ts}
│   ├── hooks/{useAnalysisStream.ts, useAnalysisStream.test.ts}
│   ├── store/appStore.ts
│   ├── components/{TabNav,HealthBadge,Markdown,Toast}.tsx + .test.tsx
│   └── pages/{Analysis,History,Config,Diagnostics}Page.tsx + .test.tsx
└── README.md

docs/frontend.md                # NEW (Phase E)
docs/backend.md                 # MODIFY (Phase E): note SPA + retired Streamlit
README.md                       # MODIFY (Phase E)
docker-compose.yml              # MODIFY (Phase E)
```

**Phases each produce working software and are independently committable/stoppable.** Within a phase, tasks are bite-sized and TDD-ordered. Dispatch one subagent per task; review between tasks.

---

# PHASE A — Scaffold + API contract + shell

Outcome: `npm run dev` serves a SPA with a header, 4-tab nav (routes), a live health badge, a fully typed API client + WS hook covered by unit tests. No business pages yet.

## Task A1: Vite + React + TS scaffold

**Files:** Create `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/.gitignore`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test-setup.ts`, `frontend/src/styles/tokens.css`, `frontend/src/styles/components.css`, `frontend/README.md`

- [ ] **Step 1: package.json**

```json
{
  "name": "tradingagents-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "zustand": "^4.5.0",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: vite.config.ts**

```ts
/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8765", changeOrigin: true },
      "/ws": {
        target: "ws://localhost:8765",
        ws: true,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/ws/, "/api/analysis/ws"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

- [ ] **Step 3: tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: index.html + test-setup.ts + main.tsx**

`frontend/index.html`:

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TradingAgents</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

`frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import App from "./App";
import "./styles/tokens.css";
import "./styles/components.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/analysis" replace /> },
      { path: "analysis", element: <div data-testid="placeholder-analysis" /> },
      { path: "history", element: <div data-testid="placeholder-history" /> },
      { path: "config", element: <div data-testid="placeholder-config" /> },
      { path: "diagnostics", element: <div data-testid="placeholder-diagnostics" /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
```

- [ ] **Step 5: styles/tokens.css + styles/components.css**

`frontend/src/styles/tokens.css`:

```css
:root {
  --c-bg: #0f172a;
  --c-surface: #1e293b;
  --c-surface-2: #334155;
  --c-border: #334155;
  --c-text: #e2e8f0;
  --c-text-dim: #94a3b8;
  --c-accent: #38bdf8;
  --c-ok: #22c55e;
  --c-warn: #f59e0b;
  --c-err: #ef4444;
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
  --sp-6: 24px; --sp-8: 32px;
  --fz-sm: 13px; --fz-md: 15px; --fz-lg: 19px; --fz-xl: 26px;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--c-bg); color: var(--c-text);
  font-family: var(--font); font-size: var(--fz-md);
}
```

`frontend/src/styles/components.css`:

```css
.btn {
  background: var(--c-accent); color: #00131f; border: 0;
  padding: var(--sp-2) var(--sp-4); border-radius: var(--radius);
  font-size: var(--fz-md); cursor: pointer; font-weight: 600;
}
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--c-text); border: 1px solid var(--c-border); }
.card {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: var(--radius); padding: var(--sp-4);
}
.tag { display: inline-block; padding: 2px var(--sp-2); border-radius: 4px;
  font-size: var(--fz-sm); background: var(--c-surface-2); }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-ok { background: var(--c-ok); } .dot-err { background: var(--c-err); }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--c-border); padding: var(--sp-2) var(--sp-3);
  text-align: left; font-size: var(--fz-sm); }
input, select, textarea {
  background: var(--c-bg); color: var(--c-text); border: 1px solid var(--c-border);
  border-radius: 6px; padding: var(--sp-2) var(--sp-3); font-size: var(--fz-md);
}
.row { display: flex; gap: var(--sp-3); align-items: center; }
.col { display: flex; flex-direction: column; gap: var(--sp-3); }
.markdown-body { font-size: var(--fz-md); line-height: 1.6; }
.markdown-body table { margin: var(--sp-3) 0; }
```

- [ ] **Step 6: App.tsx**

```tsx
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
```

(`TabNav`, `HealthBadge`, `Toast` are created in A2/B1 — the build in Step 8 will surface them as missing until then; that is expected and noted.)

- [ ] **Step 7: README + .gitignore**

`frontend/.gitignore`:

```
node_modules
dist
*.log
```

`frontend/README.md`:

```markdown
# TradingAgents Frontend

Vite + React + TS SPA over the FastAPI backend.

## Dev
\`\`\`bash
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api + /ws → :8765)
\`\`\`
Run the backend first: `uvicorn backend.main:app --port 8765` (repo root).

## Test / Build
\`\`\`bash
npm test            # vitest (jsdom, mocked fetch/WS — no backend needed)
npm run build       # tsc -b && vite build → dist/
\`\`\`
```

- [ ] **Step 8: Install + verify**

Run: `cd frontend && npm install`
Expected: completes without error. If `npm install` itself fails, STOP and report BLOCKED.
(`npm run build` will fail here because `TabNav/HealthBadge/Toast` don't exist yet — that is expected and resolved in A2/B1. Do NOT create stubs for them in this task; A2/B1 own them.)

- [ ] **Step 9: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): Vite+React+TS scaffold, design tokens, app shell (Step 2 A1)"
```

## Task A2: Typed API client + types + TabNav + HealthBadge

**Files:** Create `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`, `frontend/src/components/TabNav.tsx`, `frontend/src/components/TabNav.test.tsx`, `frontend/src/components/HealthBadge.tsx`, `frontend/src/components/HealthBadge.test.tsx`

- [ ] **Step 1: client.test.ts (failing)**

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response);
}

beforeEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("getHealth GETs /api/health", async () => {
    const f = mockFetch(200, { status: "ok" });
    vi.stubGlobal("fetch", f);
    expect(await api.getHealth()).toEqual({ status: "ok" });
    expect(f).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
  });

  it("startAnalysis POSTs body", async () => {
    const f = mockFetch(200, { run_id: "abc123" });
    vi.stubGlobal("fetch", f);
    const r = await api.startAnalysis({ ticker: "AAPL", trade_date: "2026-01-02", config_overrides: {} });
    expect(f).toHaveBeenCalledWith("/api/analysis/start", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: "AAPL", trade_date: "2026-01-02", config_overrides: {} }),
    }));
    expect(r.run_id).toBe("abc123");
  });

  it("abortAnalysis POSTs to /{id}/abort", async () => {
    const f = mockFetch(200, { run_id: "x", accepted: true });
    vi.stubGlobal("fetch", f);
    await api.abortAnalysis("x");
    expect(f).toHaveBeenCalledWith("/api/analysis/x/abort", expect.objectContaining({ method: "POST" }));
  });

  it("listHistory with and without ticker", async () => {
    const f = mockFetch(200, { items: [] });
    vi.stubGlobal("fetch", f);
    await api.listHistory("AAPL");
    await api.listHistory();
    expect(f).toHaveBeenNthCalledWith(1, "/api/history?ticker=AAPL", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/history", expect.objectContaining({ method: "GET" }));
  });

  it("patchHistory PATCHes", async () => {
    const f = mockFetch(200, { ticker: "AAPL", trade_date: "2026-01-02", updated: true });
    vi.stubGlobal("fetch", f);
    await api.patchHistory("AAPL", "2026-01-02", { note: "hi" });
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-02",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ note: "hi" }) }));
  });

  it("getDiff GETs the diff path", async () => {
    const f = mockFetch(200, { a: {}, b: {}, sections: {} });
    vi.stubGlobal("fetch", f);
    await api.getDiff("AAPL", "2026-01-01", "AAPL", "2026-02-01");
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-01/diff/AAPL/2026-02-01",
      expect.objectContaining({ method: "GET" }));
  });

  it("diagnostics get + run", async () => {
    const f = mockFetch(200, { degraded: [], checked_at: "t" });
    vi.stubGlobal("fetch", f);
    await api.getDiagnostics();
    await api.runDiagnostics();
    expect(f).toHaveBeenNthCalledWith(1, "/api/diagnostics", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/diagnostics/run", expect.objectContaining({ method: "POST" }));
  });

  it("providers list/setkey/test", async () => {
    const f = mockFetch(200, { providers: [] });
    vi.stubGlobal("fetch", f);
    await api.listProviders();
    await api.setProviderKey("deepseek", "sk-x");
    await api.testProvider("deepseek");
    expect(f).toHaveBeenNthCalledWith(1, "/api/providers", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/providers/deepseek/key",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ api_key: "sk-x" }) }));
    expect(f).toHaveBeenNthCalledWith(3, "/api/providers/deepseek/test",
      expect.objectContaining({ method: "POST" }));
  });

  it("pdfUrl builds the path (no fetch)", () => {
    expect(api.pdfUrl("AAPL", "2026-01-02")).toBe("/api/runs/AAPL/2026-01-02/pdf");
  });

  it("throws ApiError with status + detail on non-2xx", async () => {
    const f = mockFetch(404, { detail: "nope" });
    vi.stubGlobal("fetch", f);
    await expect(api.listHistory("X")).rejects.toMatchObject({ status: 404, detail: "nope" });
  });
});
```

- [ ] **Step 2: Run → fail.** `cd frontend && npx vitest run src/api/client.test.ts` → FAIL (no exports).

- [ ] **Step 3: types.ts**

```ts
export interface Health { status: string; }
export interface StartAnalysisRequest {
  ticker: string; trade_date: string; config_overrides: Record<string, unknown>;
}
export interface StartAnalysisResponse { run_id: string; }
export interface AbortResponse { run_id: string; accepted: boolean; }

export type WsEvent =
  | { type: "status"; status: string }
  | { type: "chunk"; payload: Record<string, unknown> }
  | { type: "done"; status: string }
  | { type: "aborted" }
  | { type: "error"; message: string }
  | { type: "ping" };

export interface HistoryItem {
  ticker: string; trade_date: string;
  rating: string | null; summary: string | null;
  model: string | null; provider: string | null;
  note: string | null; user_rating: string | null;
  created_at: string; json_path: string;
}
export interface HistoryListResponse { items: HistoryItem[]; }
export interface PatchHistoryRequest { note?: string; rating?: string; }

export interface DiffSection { changed: boolean; diff: string; }
export interface DiffResponse {
  a: { ticker: string; trade_date: string };
  b: { ticker: string; trade_date: string };
  sections: Record<string, DiffSection>;
}

export interface DiagnosticsResponse { degraded: string[]; checked_at: string; }

export interface ProviderInfo {
  id: string; name: string;
  env_var: string | null; base_url: string | null; configured: boolean;
}
export interface ProviderListResponse { providers: ProviderInfo[]; }
export interface SetKeyResponse { id: string; configured: boolean; }
export interface TestProviderResponse {
  id: string; ok: boolean; reason: string; status?: number | null;
}
```

- [ ] **Step 4: client.ts**

```ts
import type {
  Health, StartAnalysisRequest, StartAnalysisResponse, AbortResponse,
  HistoryListResponse, PatchHistoryRequest, DiffResponse,
  DiagnosticsResponse, ProviderListResponse, SetKeyResponse, TestProviderResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function req<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, { method: "GET", ...init });
  if (!resp.ok) {
    let detail: unknown = null;
    try { detail = (await resp.json())?.detail ?? null; } catch { /* non-JSON */ }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const getHealth = () => req<Health>("/api/health", { method: "GET" });

export const startAnalysis = (b: StartAnalysisRequest) =>
  req<StartAnalysisResponse>("/api/analysis/start", jsonBody("POST", b));

export const abortAnalysis = (runId: string) =>
  req<AbortResponse>(`/api/analysis/${encodeURIComponent(runId)}/abort`, { method: "POST" });

export const listHistory = (ticker?: string) =>
  req<HistoryListResponse>(
    ticker ? `/api/history?ticker=${encodeURIComponent(ticker)}` : "/api/history",
    { method: "GET" }
  );

export const patchHistory = (ticker: string, tradeDate: string, b: PatchHistoryRequest) =>
  req<{ ticker: string; trade_date: string; updated: boolean }>(
    `/api/history/${encodeURIComponent(ticker)}/${encodeURIComponent(tradeDate)}`,
    jsonBody("PATCH", b)
  );

export const getDiff = (t1: string, d1: string, t2: string, d2: string) =>
  req<DiffResponse>(
    `/api/history/${encodeURIComponent(t1)}/${encodeURIComponent(d1)}/diff/${encodeURIComponent(t2)}/${encodeURIComponent(d2)}`,
    { method: "GET" }
  );

export const getDiagnostics = () => req<DiagnosticsResponse>("/api/diagnostics", { method: "GET" });
export const runDiagnostics = () => req<DiagnosticsResponse>("/api/diagnostics/run", { method: "POST" });

export const listProviders = () => req<ProviderListResponse>("/api/providers", { method: "GET" });
export const setProviderKey = (id: string, apiKey: string) =>
  req<SetKeyResponse>(`/api/providers/${encodeURIComponent(id)}/key`, jsonBody("POST", { api_key: apiKey }));
export const testProvider = (id: string) =>
  req<TestProviderResponse>(`/api/providers/${encodeURIComponent(id)}/test`, { method: "POST" });

export const pdfUrl = (ticker: string, tradeDate: string) =>
  `/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(tradeDate)}/pdf`;
```

- [ ] **Step 5: Run client test → PASS.** `cd frontend && npx vitest run src/api/client.test.ts` (encodeURIComponent of `AAPL`/`2026-01-02`/`deepseek` is identity → asserted URLs match).

- [ ] **Step 6: TabNav test + impl**

`frontend/src/components/TabNav.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { it, expect } from "vitest";
import TabNav from "./TabNav";

it("renders 4 tab links with correct hrefs", () => {
  render(<MemoryRouter initialEntries={["/analysis"]}><TabNav /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "分析" })).toHaveAttribute("href", "/analysis");
  expect(screen.getByRole("link", { name: "历史" })).toHaveAttribute("href", "/history");
  expect(screen.getByRole("link", { name: "配置" })).toHaveAttribute("href", "/config");
  expect(screen.getByRole("link", { name: "诊断" })).toHaveAttribute("href", "/diagnostics");
});
```

`frontend/src/components/TabNav.tsx`:

```tsx
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
```

- [ ] **Step 7: HealthBadge test + impl**

`frontend/src/components/HealthBadge.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, it, expect } from "vitest";
import HealthBadge from "./HealthBadge";

beforeEach(() => vi.restoreAllMocks());

it("ok dot when health ok", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ status: "ok" }),
  } as unknown as Response));
  render(<HealthBadge />);
  await waitFor(() => expect(screen.getByTestId("health-dot")).toHaveClass("dot-ok"));
});

it("err dot when health fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<HealthBadge />);
  await waitFor(() => expect(screen.getByTestId("health-dot")).toHaveClass("dot-err"));
});
```

`frontend/src/components/HealthBadge.tsx`:

```tsx
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
```

- [ ] **Step 8: Run targeted tests → PASS** (`client`, `TabNav`, `HealthBadge`). Full `npm test` + `npm run build` will still fail until `Toast` exists (B1) — that is expected; do NOT create `Toast` here.

- [ ] **Step 9: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): typed API client, WS types, TabNav, HealthBadge (Step 2 A2)"
```

## Task A3: useAnalysisStream hook + Zustand store + Toast (unblocks build)

**Files:** Create `frontend/src/hooks/useAnalysisStream.ts`, `frontend/src/hooks/useAnalysisStream.test.ts`, `frontend/src/store/appStore.ts`, `frontend/src/components/Toast.tsx`, `frontend/src/components/Toast.test.tsx`

- [ ] **Step 1: useAnalysisStream.test.ts (failing, mock WebSocket)**

```ts
import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAnalysisStream } from "./useAnalysisStream";

class FakeWS {
  static last: FakeWS;
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) { this.url = url; FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.(); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

beforeEach(() => vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket));

describe("useAnalysisStream", () => {
  it("connects to ws path and accumulates chunks", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-1"));
    expect(FakeWS.last.url).toContain("/ws/run-1");
    act(() => FakeWS.last.emit({ type: "status", status: "running" }));
    await waitFor(() => expect(result.current.status).toBe("running"));
    act(() => FakeWS.last.emit({ type: "chunk", payload: { market_report: "m1" } }));
    act(() => FakeWS.last.emit({ type: "chunk", payload: { final_trade_decision: "BUY" } }));
    await waitFor(() => {
      expect(result.current.report.market_report).toBe("m1");
      expect(result.current.report.final_trade_decision).toBe("BUY");
    });
  });

  it("done closes the socket", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-2"));
    act(() => FakeWS.last.emit({ type: "done", status: "done" }));
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(FakeWS.last.closed).toBe(true);
  });

  it("error captures message", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-3"));
    act(() => FakeWS.last.emit({ type: "error", message: "boom" }));
    await waitFor(() => {
      expect(result.current.status).toBe("error");
      expect(result.current.error).toBe("boom");
    });
  });

  it("ping does not change status", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-4"));
    act(() => FakeWS.last.emit({ type: "status", status: "running" }));
    act(() => FakeWS.last.emit({ type: "ping" }));
    await waitFor(() => expect(result.current.status).toBe("running"));
  });

  it("disconnect closes + resets", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-5"));
    act(() => result.current.disconnect());
    expect(FakeWS.last.closed).toBe(true);
    expect(result.current.status).toBe("idle");
  });
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: useAnalysisStream.ts**

```ts
import { useCallback, useRef, useState } from "react";
import type { WsEvent } from "../api/types";

export type StreamStatus = "idle" | "running" | "done" | "aborted" | "error";

export interface StreamState {
  status: StreamStatus;
  report: Record<string, unknown>;
  error: string | null;
  chunkCount: number;
  connect: (runId: string) => void;
  disconnect: () => void;
}

function wsUrl(runId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/${encodeURIComponent(runId)}`;
}

export function useAnalysisStream(): StreamState {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [report, setReport] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [chunkCount, setChunkCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("idle");
    setReport({});
    setError(null);
    setChunkCount(0);
  }, []);

  const connect = useCallback((runId: string) => {
    wsRef.current?.close();
    setStatus("running");
    setReport({});
    setError(null);
    setChunkCount(0);
    const ws = new WebSocket(wsUrl(runId));
    wsRef.current = ws;
    ws.onmessage = (e: MessageEvent) => {
      const ev = JSON.parse(e.data) as WsEvent;
      switch (ev.type) {
        case "status":
          setStatus(ev.status === "running" ? "running" : (ev.status as StreamStatus));
          break;
        case "chunk":
          setReport((r) => ({ ...r, ...ev.payload }));
          setChunkCount((n) => n + 1);
          break;
        case "done":
          setStatus("done"); ws.close(); break;
        case "aborted":
          setStatus("aborted"); ws.close(); break;
        case "error":
          setStatus("error"); setError(ev.message); ws.close(); break;
        case "ping":
          break;
      }
    };
    ws.onerror = () => { setStatus("error"); setError("WebSocket connection error"); };
  }, []);

  return { status, report, error, chunkCount, connect, disconnect };
}
```

- [ ] **Step 4: Run hook test → PASS.**

- [ ] **Step 5: store/appStore.ts**

```ts
import { create } from "zustand";

interface Toast { id: number; kind: "ok" | "err"; text: string; }

interface AppState {
  toasts: Toast[];
  pushToast: (kind: "ok" | "err", text: string) => void;
  dismissToast: (id: number) => void;
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;
}

let toastSeq = 1;

export const useAppStore = create<AppState>((set) => ({
  toasts: [],
  pushToast: (kind, text) => set((s) => ({ toasts: [...s.toasts, { id: toastSeq++, kind, text }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  activeRunId: null,
  setActiveRunId: (id) => set({ activeRunId: id }),
}));
```

- [ ] **Step 6: Toast test + impl**

`frontend/src/components/Toast.test.tsx`:

```tsx
import { render, screen, act } from "@testing-library/react";
import { it, expect } from "vitest";
import Toast from "./Toast";
import { useAppStore } from "../store/appStore";

it("renders queued toasts from the store", () => {
  render(<Toast />);
  act(() => useAppStore.getState().pushToast("err", "boom"));
  expect(screen.getByText("boom")).toBeInTheDocument();
});
```

`frontend/src/components/Toast.tsx`:

```tsx
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
```

- [ ] **Step 7: Full suite + build (now unblocked).** `cd frontend && npm test && npm run build` → ALL pass; `tsc -b && vite build` succeeds (placeholders keep routes valid; App imports all resolve).

- [ ] **Step 8: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): useAnalysisStream hook, Zustand store, Toast — build green (Step 2 A3)"
```

---

# PHASE B — Diagnostics + History (read-only, low risk)

## Task B1: Markdown component

**Files:** Create `frontend/src/components/Markdown.tsx`, `frontend/src/components/Markdown.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import Markdown from "./Markdown";

it("renders headings and gfm tables", () => {
  render(<Markdown>{"# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |"}</Markdown>);
  expect(screen.getByRole("heading", { name: "Title" })).toBeInTheDocument();
  expect(screen.getByRole("table")).toBeInTheDocument();
});

it("renders empty string without crashing", () => {
  const { container } = render(<Markdown>{""}</Markdown>);
  expect(container).toBeInTheDocument();
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Impl** `frontend/src/components/Markdown.tsx`:

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ""}</ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 4: Run → PASS. `npm test && npm run build`.**

- [ ] **Step 5: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): Markdown component (Step 2 B1)"
```

## Task B2: Diagnostics page

**Files:** Create `frontend/src/pages/DiagnosticsPage.tsx`, `frontend/src/pages/DiagnosticsPage.test.tsx`; Modify `frontend/src/main.tsx`

- [ ] **Step 1: Test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import DiagnosticsPage from "./DiagnosticsPage";

beforeEach(() => vi.restoreAllMocks());

it("lists degraded sources", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ degraded: ["akshare 未安装"], checked_at: "2026-01-01T00:00:00Z" }),
  } as unknown as Response));
  render(<DiagnosticsPage />);
  await waitFor(() => expect(screen.getByText("akshare 未安装")).toBeInTheDocument());
});

it("all-clear when empty", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ degraded: [], checked_at: "t" }),
  } as unknown as Response));
  render(<DiagnosticsPage />);
  await waitFor(() => expect(screen.getByText(/全部数据源正常/)).toBeInTheDocument());
});

it("re-run calls POST /api/diagnostics/run", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ degraded: [], checked_at: "t" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<DiagnosticsPage />);
  await waitFor(() => screen.getByText(/全部数据源正常/));
  await userEvent.click(screen.getByRole("button", { name: "重新检测" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/diagnostics/run", expect.objectContaining({ method: "POST" })));
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Impl** `frontend/src/pages/DiagnosticsPage.tsx`:

```tsx
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
```

In `frontend/src/main.tsx`: add `import DiagnosticsPage from "./pages/DiagnosticsPage";` and replace the diagnostics placeholder element with `<DiagnosticsPage />`.

- [ ] **Step 4: Run page test → PASS. `npm test && npm run build`.**

- [ ] **Step 5: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): Diagnostics page (Step 2 B2)"
```

## Task B3: History page

**Files:** Create `frontend/src/pages/HistoryPage.tsx`, `frontend/src/pages/HistoryPage.test.tsx`; Modify `frontend/src/main.tsx`

- [ ] **Step 1: Test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import HistoryPage from "./HistoryPage";

const ITEM = {
  ticker: "AAPL", trade_date: "2026-01-02", rating: "Buy",
  summary: "strong", model: "deepseek", provider: "DeepSeek",
  note: null, user_rating: null, created_at: "2026-01-02T10:00:00Z",
  json_path: "/x/AAPL/2026-01-02/final_state_report.json",
};

beforeEach(() => vi.restoreAllMocks());

function fetchMock(handler: (url: string, init?: RequestInit) => unknown) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true, status: 200, json: async () => handler(url, init),
  } as unknown as Response));
}

it("renders history rows", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ items: [ITEM] })));
  render(<HistoryPage />);
  await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
  expect(screen.getByText("Buy")).toBeInTheDocument();
});

it("filters by ticker", async () => {
  const f = fetchMock(() => ({ items: [ITEM] }));
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByText("AAPL"));
  await userEvent.type(screen.getByPlaceholderText("按 ticker 过滤"), "AAPL");
  await userEvent.click(screen.getByRole("button", { name: "查询" }));
  await waitFor(() =>
    expect(f).toHaveBeenLastCalledWith("/api/history?ticker=AAPL", expect.objectContaining({ method: "GET" })));
});

it("saves a note via PATCH", async () => {
  const f = fetchMock((url, init) =>
    init?.method === "PATCH" ? { ticker: "AAPL", trade_date: "2026-01-02", updated: true } : { items: [ITEM] });
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByText("AAPL"));
  await userEvent.click(screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  await userEvent.type(await screen.findByPlaceholderText("备注"), "looks good");
  await userEvent.click(screen.getByRole("button", { name: "保存备注" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-02",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ note: "looks good" }) })));
});

it("PDF link points at the runs endpoint", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ items: [ITEM] })));
  render(<HistoryPage />);
  await waitFor(() => screen.getByText("AAPL"));
  await userEvent.click(screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  expect(await screen.findByRole("link", { name: "下载 PDF" }))
    .toHaveAttribute("href", "/api/runs/AAPL/2026-01-02/pdf");
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Impl** `frontend/src/pages/HistoryPage.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { listHistory, patchHistory, pdfUrl } from "../api/client";
import type { HistoryItem } from "../api/types";
import { useAppStore } from "../store/appStore";

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState("");
  const pushToast = useAppStore((s) => s.pushToast);

  const load = useCallback((ticker?: string) => {
    listHistory(ticker || undefined)
      .then((r) => setItems(r.items))
      .catch((e) => pushToast("err", `加载历史失败: ${e.status ?? e}`));
  }, [pushToast]);

  useEffect(() => { load(); }, [load]);

  const open = (it: HistoryItem) => {
    setSelected(it);
    setNote(it.note ?? "");
    setRating(it.user_rating ?? "");
  };

  const save = async () => {
    if (!selected) return;
    try {
      const body: { note?: string; rating?: string } = {};
      if (note) body.note = note;
      if (rating) body.rating = rating;
      await patchHistory(selected.ticker, selected.trade_date, body);
      pushToast("ok", "已保存");
      load(filter || undefined);
    } catch (e: any) {
      pushToast("err", `保存失败: ${e.status ?? e}`);
    }
  };

  return (
    <div className="col">
      <h2>历史分析</h2>
      <div className="row">
        <input placeholder="按 ticker 过滤" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button className="btn" onClick={() => load(filter || undefined)}>查询</button>
      </div>
      <table>
        <thead><tr><th>Ticker</th><th>日期</th><th>评级</th><th>模型</th><th>时间</th></tr></thead>
        <tbody>
          {items.map((it) => (
            <tr key={`${it.ticker}/${it.trade_date}`}>
              <td>
                <button className="btn-ghost" onClick={() => open(it)}>{it.ticker} {it.trade_date}</button>
              </td>
              <td>{it.trade_date}</td>
              <td>{it.rating ?? "—"}</td>
              <td>{it.model ?? "—"}</td>
              <td>{it.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && (
        <div className="card col">
          <h3>{selected.ticker} · {selected.trade_date}</h3>
          <div style={{ color: "var(--c-text-dim)" }}>{selected.summary}</div>
          <textarea placeholder="备注" value={note} onChange={(e) => setNote(e.target.value)} />
          <input placeholder="评分 (good/bad/…)" value={rating} onChange={(e) => setRating(e.target.value)} />
          <div className="row">
            <button className="btn" onClick={save}>保存备注</button>
            <a className="btn-ghost" href={pdfUrl(selected.ticker, selected.trade_date)}
               target="_blank" rel="noreferrer"
               style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)" }}>下载 PDF</a>
          </div>
        </div>
      )}
    </div>
  );
}
```

In `main.tsx`: import `HistoryPage`, replace the history placeholder element.

- [ ] **Step 4: Run page test → PASS. `npm test && npm run build`.**

- [ ] **Step 5: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): History page — list/filter/note/rating/pdf (Step 2 B3)"
```

---

# PHASE C — Config / Providers tab

## Task C1: Config page

**Files:** Create `frontend/src/pages/ConfigPage.tsx`, `frontend/src/pages/ConfigPage.test.tsx`; Modify `frontend/src/main.tsx`

- [ ] **Step 1: Test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import ConfigPage from "./ConfigPage";

const PROVIDERS = {
  providers: [
    { id: "deepseek", name: "deepseek", env_var: "DEEPSEEK_API_KEY", base_url: "https://api.deepseek.com", configured: true },
    { id: "volcengine", name: "volcengine", env_var: "ARK_API_KEY", base_url: "https://ark...", configured: false },
  ],
};

beforeEach(() => vi.restoreAllMocks());

function fetchMock(handler: (url: string, init?: RequestInit) => { status?: number; body: unknown }) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = handler(url, init);
    return { ok: status < 300, status, json: async () => body } as unknown as Response;
  });
}

it("lists providers, never shows a key", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ body: PROVIDERS })));
  render(<ConfigPage />);
  await waitFor(() => expect(screen.getByText("deepseek")).toBeInTheDocument());
  expect(screen.getByText("volcengine")).toBeInTheDocument();
  expect(screen.queryByText(/sk-/)).toBeNull();
});

it("submits a key", async () => {
  const f = fetchMock((url, init) =>
    init?.method === "POST" && url.endsWith("/key")
      ? { body: { id: "volcengine", configured: true } } : { body: PROVIDERS });
  vi.stubGlobal("fetch", f);
  render(<ConfigPage />);
  await waitFor(() => screen.getByText("volcengine"));
  await userEvent.type(screen.getByTestId("key-input-volcengine"), "ark-secret");
  await userEvent.click(screen.getByTestId("key-save-volcengine"));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/providers/volcengine/key",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ api_key: "ark-secret" }) })));
});

it("test button shows result", async () => {
  const f = fetchMock((url, init) =>
    init?.method === "POST" && url.endsWith("/test")
      ? { body: { id: "deepseek", ok: true, reason: "reachable", status: 200 } } : { body: PROVIDERS });
  vi.stubGlobal("fetch", f);
  render(<ConfigPage />);
  await waitFor(() => screen.getByText("deepseek"));
  await userEvent.click(screen.getByTestId("key-test-deepseek"));
  await waitFor(() => expect(screen.getByText(/reachable/)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Impl** `frontend/src/pages/ConfigPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { listProviders, setProviderKey, testProvider } from "../api/client";
import type { ProviderInfo, TestProviderResponse } from "../api/types";
import { useAppStore } from "../store/appStore";

export default function ConfigPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, TestProviderResponse>>({});
  const pushToast = useAppStore((s) => s.pushToast);

  const load = () =>
    listProviders().then((r) => setProviders(r.providers))
      .catch((e) => pushToast("err", `加载 providers 失败: ${e.status ?? e}`));
  useEffect(() => { load(); }, []);

  const saveKey = async (id: string) => {
    try {
      await setProviderKey(id, keys[id] ?? "");
      pushToast("ok", `${id} key 已保存`);
      setKeys((k) => ({ ...k, [id]: "" }));
      load();
    } catch (e: any) {
      pushToast("err", `保存失败 (${e.status ?? e})`);
    }
  };

  const runTest = async (id: string) => {
    try {
      const r = await testProvider(id);
      setResults((m) => ({ ...m, [id]: r }));
    } catch (e: any) {
      pushToast("err", `测试失败 (${e.status ?? e})`);
    }
  };

  return (
    <div className="col">
      <h2>Provider 配置</h2>
      <p style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
        API key 只写不回显。提交后写入 .env + 进程环境。
      </p>
      <table>
        <thead><tr><th>Provider</th><th>已配置</th><th>设置 Key</th><th>测试</th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id}>
              <td>{p.name}<div style={{ color: "var(--c-text-dim)", fontSize: 12 }}>{p.base_url ?? "—"}</div></td>
              <td><span className={`dot ${p.configured ? "dot-ok" : "dot-err"}`} /> {p.configured ? "是" : "否"}</td>
              <td>
                <div className="row">
                  <input type="password" placeholder="API Key" data-testid={`key-input-${p.id}`}
                    value={keys[p.id] ?? ""}
                    onChange={(e) => setKeys((k) => ({ ...k, [p.id]: e.target.value }))} />
                  <button className="btn" data-testid={`key-save-${p.id}`} onClick={() => saveKey(p.id)}>保存</button>
                </div>
              </td>
              <td>
                <button className="btn-ghost" data-testid={`key-test-${p.id}`} onClick={() => runTest(p.id)}>测试</button>
                {results[p.id] && (
                  <div style={{ fontSize: 12, color: results[p.id].ok ? "var(--c-ok)" : "var(--c-err)" }}>
                    {results[p.id].reason}{results[p.id].status ? ` (${results[p.id].status})` : ""}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

In `main.tsx`: import `ConfigPage`, replace the config placeholder element.

- [ ] **Step 4: Run page test → PASS. `npm test && npm run build`.**

- [ ] **Step 5: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): Config/Providers page — list/setkey/test (Step 2 C1)"
```

---

# PHASE D — Analysis tab (streaming — the hard one)

## Task D1: Analysis page

**Files:** Create `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/pages/AnalysisPage.test.tsx`; Modify `frontend/src/main.tsx`

- [ ] **Step 1: Test (mock fetch for start/abort + FakeWS for stream)**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import AnalysisPage from "./AnalysisPage";

class FakeWS {
  static last: FakeWS;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.(); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
});

it("start posts the form, connects stream, renders markdown chunks, reaches done", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r1" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);

  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("Ticker"), "AAPL");
  await userEvent.type(screen.getByLabelText("交易日期"), "2026-01-02");
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));

  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/analysis/start", expect.objectContaining({ method: "POST" })));
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r1"));

  FakeWS.last.emit({ type: "status", status: "running" });
  FakeWS.last.emit({ type: "chunk", payload: { market_report: "# Market\nstrong buy" } });
  await waitFor(() => expect(screen.getByRole("heading", { name: "Market" })).toBeInTheDocument());

  FakeWS.last.emit({ type: "done", status: "done" });
  await waitFor(() => expect(screen.getByText(/已完成/)).toBeInTheDocument());
});

it("abort posts to the abort endpoint", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r2", accepted: true }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("Ticker"), "AAPL");
  await userEvent.type(screen.getByLabelText("交易日期"), "2026-01-02");
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r2"));
  FakeWS.last.emit({ type: "status", status: "running" });
  await userEvent.click(await screen.findByRole("button", { name: "中止" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/analysis/r2/abort", expect.objectContaining({ method: "POST" })));
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Impl** `frontend/src/pages/AnalysisPage.tsx`:

```tsx
import { useState } from "react";
import { startAnalysis, abortAnalysis, pdfUrl } from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import Markdown from "../components/Markdown";
import { useAppStore } from "../store/appStore";

const REPORT_KEYS: { key: string; label: string }[] = [
  { key: "market_report", label: "市场分析" },
  { key: "sentiment_report", label: "社交情绪" },
  { key: "news_report", label: "新闻分析" },
  { key: "fundamentals_report", label: "基本面" },
  { key: "investment_plan", label: "研究决策" },
  { key: "trader_investment_plan", label: "交易计划" },
  { key: "final_trade_decision", label: "最终决策" },
];

export default function AnalysisPage() {
  const [ticker, setTicker] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const stream = useAnalysisStream();
  const pushToast = useAppStore((s) => s.pushToast);

  const start = async () => {
    try {
      const { run_id } = await startAnalysis({ ticker, trade_date: tradeDate, config_overrides: {} });
      setRunId(run_id);
      stream.connect(run_id);
    } catch (e: any) {
      pushToast("err", `启动失败: ${e.status ?? e}`);
    }
  };

  const abort = async () => {
    if (!runId) return;
    try { await abortAnalysis(runId); } catch (e: any) { pushToast("err", `中止失败: ${e.status ?? e}`); }
  };

  const running = stream.status === "running";

  return (
    <div className="col">
      <h2>分析中心</h2>
      <div className="card row" style={{ flexWrap: "wrap" }}>
        <label className="col" style={{ gap: 4 }}>
          Ticker
          <input aria-label="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </label>
        <label className="col" style={{ gap: 4 }}>
          交易日期
          <input aria-label="交易日期" placeholder="YYYY-MM-DD" value={tradeDate}
            onChange={(e) => setTradeDate(e.target.value)} />
        </label>
        <button className="btn" disabled={running || !ticker || !tradeDate} onClick={start}>开始分析</button>
        {running && <button className="btn-ghost" onClick={abort}>中止</button>}
        <span style={{ color: "var(--c-text-dim)" }}>
          状态:{" "}
          {stream.status === "idle" ? "待命"
            : stream.status === "running" ? `分析中 (${stream.chunkCount} chunk)`
            : stream.status === "done" ? "已完成"
            : stream.status === "aborted" ? "已中止"
            : `错误: ${stream.error}`}
        </span>
      </div>

      {REPORT_KEYS.map(({ key, label }) => {
        const val = stream.report[key] as string | undefined;
        if (!val) return null;
        return (
          <div key={key} className="card">
            <h3>{label}</h3>
            <Markdown>{val}</Markdown>
          </div>
        );
      })}

      {stream.status === "done" && runId && ticker && tradeDate && (
        <a className="btn-ghost" href={pdfUrl(ticker, tradeDate)} target="_blank" rel="noreferrer"
           style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)", width: "fit-content" }}>
          下载本次 PDF
        </a>
      )}
    </div>
  );
}
```

In `main.tsx`: import `AnalysisPage`, replace the analysis placeholder element. (The index `<Navigate to="/analysis">` already targets it.)

- [ ] **Step 4: Run page test → PASS. `npm test && npm run build`.**

- [ ] **Step 5: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add frontend/
git commit -m "feat(frontend): Analysis page — start/stream/abort/markdown/pdf (Step 2 D1)"
```

## Task D2: Real-LLM end-to-end smoke test (manual, GATED)

Manual verification. Spends real LLM credits + needs the user's keys. **Do NOT run Step 4 without explicit user confirmation in the live session.**

- [ ] **Step 1:** Backend up: `uvicorn backend.main:app --port 8765` (repo root, `.env` sourced).
- [ ] **Step 2:** Frontend up: `cd frontend && npm run dev` → open `http://localhost:5173`.
- [ ] **Step 3:** Health badge green; Diagnostics loads; History lists prior runs; Config lists providers with correct configured dots.
- [ ] **Step 4 (GATED — confirm with user first; spends credits):** Analysis tab, ticker `AAPL`, recent trading day, 开始分析 → status 分析中, report cards stream + render Markdown, status 已完成, 下载本次 PDF returns a PDF. Start another, 中止 within ~5s → status 已中止.
- [ ] **Step 5:** No commit (manual). If anything fails, fix the relevant Phase-D task and re-run.

---

# PHASE E — Cutover (retire Streamlit from docs/Docker; keep CLI)

## Task E1: Docs + Docker cutover

**Files:** Create `docs/frontend.md`; Modify `docs/backend.md`, `README.md`, `docker-compose.yml`

- [ ] **Step 1: Create docs/frontend.md**

```markdown
# Frontend (React + Vite)

SPA over the FastAPI backend. 4 tabs: 分析 / 历史 / 配置 / 诊断.

## Dev
\`\`\`bash
uvicorn backend.main:app --port 8765        # terminal 1 (repo root)
cd frontend && npm install && npm run dev   # terminal 2 → http://localhost:5173
\`\`\`
Dev server proxies `/api` and `/ws` to `:8765`.

## Build / Test
\`\`\`bash
cd frontend
npm test            # vitest, mocked fetch/WS, no backend needed
npm run build       # → frontend/dist/ (static)
\`\`\`

## Architecture
- `src/api/client.ts` — one typed wrapper per backend endpoint
- `src/hooks/useAnalysisStream.ts` — WebSocket lifecycle for live analysis
- `src/store/appStore.ts` — Zustand (toasts, active run)
- `src/pages/*` — one component per tab
```

- [ ] **Step 2: Update README.md** — read it; replace any `streamlit run webapp.py` instruction with the two-process flow (backend + frontend) and link `docs/frontend.md` + `docs/backend.md`. Keep the CLI section (`python -m cli.main`) unchanged. If no streamlit reference exists, add a "Web UI (React + FastAPI)" section.

- [ ] **Step 3: Update docs/backend.md** — add one line under the intro: "The browser client is the React SPA in `frontend/` (see `docs/frontend.md`); Streamlit `webapp.py` is retired and no longer the supported UI." Do not delete the rollback section.

- [ ] **Step 4: Update docker-compose.yml** — read it; replace the streamlit service with `backend` (`uvicorn backend.main:app --host 0.0.0.0 --port 8765`) + `frontend` (build `frontend/`, serve `dist/`, or `npm run dev`). Preserve results-dir/`.env` volume + env wiring. If a clean split is risky, instead comment out the streamlit command + add a documented TODO referencing this plan — do NOT silently break the compose.

- [ ] **Step 5: Verify** `grep -rn "streamlit run\|webapp" README.md docker-compose.yml docs/ | grep -iv "retired\|frontend.md\|backend.md"` → no instruction still telling users to launch Streamlit as the primary UI.

- [ ] **Step 6: Commit**

```bash
cd /Users/tonniclaw/TradingAgents-WebUI
git add docs/frontend.md docs/backend.md README.md docker-compose.yml
git commit -m "docs: cut over to React SPA + FastAPI; retire Streamlit as primary UI (Step 2 E1)"
```

## Task E2: Final verification + tag

- [ ] **Step 1:** `cd frontend && npm test` → ALL vitest suites pass (client, hook, components, 4 pages).
- [ ] **Step 2:** `cd frontend && npm run build` → `tsc -b` clean (strict, noUnusedLocals) + `vite build` → `frontend/dist/`.
- [ ] **Step 3:** Backend untouched: `cd /Users/tonniclaw/TradingAgents-WebUI && pytest tests/backend/ -q --no-header` (watchdog idiom) → same 42 pass. `pytest tests/ --ignore=tests/backend -q --no-header` → same 6 pre-existing failures, no new.
- [ ] **Step 4:** Tag:

```bash
git tag -a step-2-react-frontend-complete -m "Step 2 — React+Vite SPA over the full backend API; Streamlit retired"
git log --oneline refs/tags/step-1a6-endpoints-complete..HEAD
```

- [ ] **Step 5:** Report the commit range (Phase A–E commits + tag, all on `main`).

---

## Self-Review (plan author)

**Spec coverage (original Step 2 brief):**
- `frontend/` Vite+React+TS — A1. ✅
- CSS split into `frontend/src/styles/{tokens,components}.css` — A1 Step 5 (no `design/index.html` exists; built fresh, documented in header). ✅
- 4 tabs as routes — A1 router + TabNav A2 + pages B/C/D. ✅
- WebSocket hook drives Analysis live updates — A3 + D1. ✅
- `react-markdown` + `remark-gfm` for agent reports — B1, used in D1. ✅
- Keep CLI, remove `streamlit run` — Phase E (de-reference; physical deletion deferred to explicit user decision, stated in scope). ✅
- All 13 REST + 1 WS endpoints consumed — client.ts (A2) covers every endpoint; pages exercise them (Diagnostics B2, History B3, Config C1, Analysis D1); PDF via `pdfUrl` link (B3/D1).

**Gap identified (documented deferral):** the brief implies a history A/B diff capability. `api.getDiff` is implemented + unit-tested in A2, but no Phase-B task builds a diff comparison UI. This is recorded, not silently dropped: a "compare two runs" view is a small follow-up using the already-tested `getDiff`. Not added as a task to keep History shippable; if wanted in Step 2, add Task B4 (compare view) before Phase E.

**Placeholder scan:** No TBD/"similar to". Every code step has full file content. Tests precede impl in every task. The cross-task build-ordering wrinkle (App.tsx imports Toast/TabNav/HealthBadge created across A2/A3) is explicitly called out in A1 Step 8, A2 Step 8, A3 Step 7 so an out-of-order executor isn't surprised — build is only asserted green at A3 Step 7 onward.

**Type consistency:** `WsEvent` union (types.ts) matches the hook switch (A3) and the pinned backend shapes. `HistoryItem` matches backend `query_analyses` row + Step 1a.5 `user_rating`/`note`. `ProviderInfo` matches Step 1a.6 `list_providers`. client.ts function names used identically across all pages. `useAnalysisStream` returns `{status, report, error, chunkCount, connect, disconnect}` — consumed exactly so in D1. `pdfUrl` is a pure string builder (no fetch) — used as an `href` in B3 + D1.

**Phasing:** A (scaffold+contract) → B (read-only) → C (config) → D (streaming) → E (cutover). Each phase ends building + green and is independently committable. D (highest risk) is last and its real-LLM step (D2 Step 4) is explicitly gated on user confirmation before spending credits.
