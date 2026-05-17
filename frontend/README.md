# TradingAgents Frontend

Vite + React + TS SPA over the FastAPI backend.

## Dev

    cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api + /ws -> :8765)

Run the backend first: uvicorn backend.main:app --port 8765 (repo root).

## Test / Build

    npm test            # vitest (jsdom, mocked fetch/WS - no backend needed)
    npm run build       # tsc -b && vite build -> dist/
