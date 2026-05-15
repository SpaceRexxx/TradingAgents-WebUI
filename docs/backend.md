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
| `TRADINGAGENTS_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | Origins allowed by CORS. **Must be a JSON array literal** when set via env (pydantic-settings parses `list[str]` as JSON, not comma-separated). |

API keys are **not** managed by this layer in Step 1a. The engine still reads them from `.env` / `.ui_prefs.json` the same way `webapp.py` does today. A future `/api/providers/*` route (Step 1a.5) will manage keys explicitly with redaction.

## Endpoints (Step 1a)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| POST | `/api/analysis/start` | Body: `{ticker, trade_date, config_overrides}`. Returns `{run_id}` |
| WS | `/api/analysis/ws/{run_id}` | Streams JSON events — types: `status`, `chunk`, `done`, `aborted`, `error`, `ping` |
| POST | `/api/analysis/{run_id}/abort` | Returns `{run_id, accepted}`; 404 if run unknown. Terminal `aborted` event appears on the WS shortly after |
| GET | `/api/history?ticker=` | List indexed analyses |
| PATCH | `/api/history/{ticker}/{trade_date}` | Body: `{note?, rating?}`. 404 if no analysis indexed for that ticker/date when setting `rating` |

Endpoints deferred to **Step 1a.6**: `/api/providers/*`, `/api/diagnostics/*`, `/api/runs/{id}/pdf`, `/api/history/{id}/diff/{otherId}`.

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

## Resolved in Step 1a.5

The 6 limitations the Step 1a review flagged are now fixed:

1. ✅ Backend runs persist `{ticker}/{date}/final_state_report.json` and are indexed (`backend/services/persistence.py`, called from the runner's success path before `mark_done`). Uses the engine's actual `results_dir` (`graph.config["results_dir"]`), not `Settings.results_dir`.
2. ✅ WS connect after a terminal run drains any buffered events then emits a synthetic terminal event immediately — no 30s hang. Fast-path returns before the `try:` so it never triggers eviction.
3. ✅ A `_drain()` helper runs before *every* terminal event (success/abort/error), so chunks never arrive after the terminal marker.
4. ✅ `RunRegistry` evicts terminal handles once their WS consumer finishes (both the fast-path and the live-loop `finally`, guarded by `is_terminal()`).
5. ✅ `POST /abort` returns `{run_id, accepted: true}` instead of a misleading `status` that was almost always `"running"`.
6. ✅ `PATCH /api/history/{ticker}/{trade_date}` returns 404 when no analysis is indexed for that ticker/date (`set_rating` now returns rows-affected).

**Residual (acknowledged, out of Step 1a.5 scope):** a run whose WebSocket is *never* connected by any client leaks its `RunHandle` for the process lifetime — eviction is WS-driven and there is no background reaper. Acceptable under the single-user local-dev model; revisit if the backend is ever multi-tenant or long-lived. Also: a PATCH carrying both `note` and `rating` for an unknown target silently no-ops the note but 404s on the rating (`set_note` was not in scope for the rows-affected change).

Still deferred to **Step 1a.6**: `/api/providers/*`, `/api/diagnostics/*`, `GET /api/runs/{id}/pdf`, `GET /api/history/{id}/diff/{otherId}`.
Still deferred to **Step 1b**: `webapp.py` → API-client migration.

## Rollback

The state immediately before Step 1a is preserved as both a tag and a branch named `pre-fastapi-refactor` (commit `b84edd6`). Because both refs share that name, use the explicit `refs/tags/` prefix to silence git's ambiguity warning:

    git reset --hard refs/tags/pre-fastapi-refactor

Or to inspect what changed:

    git diff refs/tags/pre-fastapi-refactor..HEAD -- backend/ tradingagents/graph/trading_graph.py tradingagents/storage/sqlite_history.py
