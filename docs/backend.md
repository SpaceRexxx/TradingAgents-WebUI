# Backend (FastAPI)

The `backend/` package wraps the existing `tradingagents/` engine with a FastAPI HTTP/WebSocket layer. It runs alongside `webapp.py` (Streamlit) — both share the same engine, results directory, and SQLite index. Step 1a does not modify `webapp.py` or `cli/`; the backend is purely additive.

## Run

```bash
uvicorn backend.main:app --port 8765 --reload
```

Open <http://localhost:8765/docs> for the auto-generated OpenAPI UI.

## Configuration

Environment variables (all prefixed `TRADINGAGENTS_`):

| Variable | Default | Description |
|---|---|---|
| `TRADINGAGENTS_RESULTS_DIR` | `~/Desktop/Stock` | Where analysis results + `analyses.sqlite` live |
| `TRADINGAGENTS_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated origins for the future React frontend |

API keys are **not** managed by this layer in Step 1a. The engine still reads them from `.env` / `.ui_prefs.json` the same way `webapp.py` does today. A future `/api/providers/*` route (Step 1a.5) will manage keys explicitly with redaction.

## Endpoints (Step 1a)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| POST | `/api/analysis/start` | Body: `{ticker, trade_date, config_overrides}`. Returns `{run_id}` |
| WS | `/api/analysis/ws/{run_id}` | Streams JSON events — types: `status`, `chunk`, `done`, `aborted`, `error`, `ping` |
| POST | `/api/analysis/{run_id}/abort` | Signals cancel; terminal event appears on the WS shortly after |
| GET | `/api/history?ticker=` | List indexed analyses |
| PATCH | `/api/history/{ticker}/{trade_date}` | Body: `{note?, rating?}` — updates the user-supplied fields |

Endpoints deferred to **Step 1a.5**: `/api/providers/*`, `/api/diagnostics/*`, `/api/runs/{id}/pdf`, `/api/history/{id}/diff/{otherId}`.

## Event payloads on `/api/analysis/ws/{run_id}`

All events are line-delimited JSON. Common fields:

- `{"type":"status","status":"running"}` — emitted when the run starts
- `{"type":"chunk","payload":{...}}` — one per LangGraph node delta; payload keys match the agent that produced output (`market_report`, `sentiment_report`, `final_trade_decision`, etc.)
- `{"type":"done","status":"done"}` — successful completion (`handle.final_state` now populated)
- `{"type":"aborted"}` — cancellation request honored
- `{"type":"error","message":"..."}` — engine exception
- `{"type":"ping"}` — 30s keep-alive when no events have flowed

## Tests

```bash
pytest tests/backend -v
```

All backend tests use an in-memory fake graph and a temp results directory — no LLM calls, no network. They run in well under 2 seconds.

For a real end-to-end smoke test against the live engine, see Task 7 in `docs/superpowers/plans/2026-05-14-step1-fastapi-backend.md`.

## Rollback

The state immediately before Step 1a is preserved as both a tag and a branch named `pre-fastapi-refactor` (commit `b84edd6`). To revert completely:

    git reset --hard pre-fastapi-refactor

Or to inspect what changed:

    git diff pre-fastapi-refactor..HEAD -- backend/ tradingagents/graph/trading_graph.py tradingagents/storage/sqlite_history.py
