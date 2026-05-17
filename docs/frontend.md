# Frontend (React + Vite)

SPA over the FastAPI backend. 4 tabs: 分析 / 历史 / 配置 / 诊断.

## Dev

    uvicorn backend.main:app --port 8765        # terminal 1 (repo root)
    cd frontend && npm install && npm run dev   # terminal 2 -> http://localhost:5173

Dev server proxies /api and /ws to :8765.

## Build / Test

    cd frontend
    npm test            # vitest, mocked fetch/WS, no backend needed
    npm run build       # -> frontend/dist/ (static)

## Architecture

- src/api/client.ts          one typed wrapper per backend endpoint
- src/hooks/useAnalysisStream.ts   WebSocket lifecycle for live analysis
- src/store/appStore.ts      Zustand (toasts, active run)
- src/pages/*                one component per tab

## Known residual

Browser DOM paint is not exercised by an automated e2e (no Playwright
bridge in CI); covered by 33 jsdom unit tests + a verified
hook<->backend WS-contract review. Backend streaming itself was
validated end-to-end with a real LLM in Step 1a (see
docs/superpowers/plans/2026-05-14-step1-fastapi-backend.md Task 7) and
via a proxy-path e2e in Step 2 D2.
