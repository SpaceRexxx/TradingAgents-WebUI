# Backend (FastAPI)

The `backend/` package wraps the existing `tradingagents/` engine with a FastAPI HTTP/WebSocket layer. It runs alongside `webapp.py` (Streamlit) — both share the same engine, results directory, and SQLite index. Step 1a does not modify `webapp.py` or `cli/`; the backend is purely additive.

The browser client is the React SPA in `frontend/` (see `docs/frontend.md`); Streamlit `webapp.py` is retired and no longer the supported UI.

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

API keys are managed by `/api/providers/{id}/key` (Step 1a.6): the key is written to `.env` + `os.environ` and is **never returned in any response or log**. `GET /api/providers` reports only `configured: bool`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| POST | `/api/analysis/start` | Body: `{ticker, trade_date, config_overrides}`. Returns `{run_id}` |
| WS | `/api/analysis/ws/{run_id}` | Streams JSON events — types: `status`, `chunk`, `done`, `aborted`, `error`, `ping` |
| POST | `/api/analysis/{run_id}/abort` | Returns `{run_id, accepted}`; 404 if run unknown. Terminal `aborted` event appears on the WS shortly after |
| GET | `/api/history?ticker=` | List indexed analyses |
| PATCH | `/api/history/{ticker}/{trade_date}` | Body: `{note?, rating?}`. 404 if no analysis indexed for that ticker/date when setting `rating` |
| GET | `/api/history/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}` | Per-section unified diff of two analyses. 404 if either side missing |
| GET | `/api/diagnostics` | `{degraded: string[], checked_at}` data-source health |
| POST | `/api/diagnostics/run` | Re-check; same shape as GET |
| GET | `/api/providers` | List providers with `configured` (never the key value) |
| POST | `/api/providers/{id}/key` | Body `{api_key}`. Writes `.env` + `os.environ`. Returns `{id, configured}`. 404 unknown, 400 keyless, 422 if key contains a newline |
| POST | `/api/providers/{id}/test` | Reachability probe of `{base_url}/models`. `{id, ok, reason, status?}` |
| GET | `/api/runs/{ticker}/{trade_date}/pdf` | Streams `application/pdf`. 404 if not indexed |

Path-identity note: the original spec wrote `/api/runs/{id}/pdf` and `.../diff/{otherId}` with opaque ids, but indexed history is keyed by `(ticker, trade_date)` — the routes use those segments instead.

All originally-deferred endpoints are now implemented. Remaining work: **Step 1b** — `webapp.py` → API-client migration.

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

**Residuals (acknowledged, out of Step 1a.5 scope):**

- A run whose WebSocket is *never* connected by any client leaks its `RunHandle` for the process lifetime — eviction is WS-driven and there is no background reaper. Acceptable under the single-user local-dev model; revisit if the backend is ever multi-tenant or long-lived.
- A PATCH carrying both `note` and `rating` for an unknown target silently no-ops the note but 404s on the rating (`set_note` was not in scope for the rows-affected change).
- **Results-dir divergence (Step 1b must address):** `persist_run` writes to the engine's `graph.config["results_dir"]`, but `GET /api/history` reads from `Settings.results_dir` (`TRADINGAGENTS_RESULTS_DIR`, default `~/Desktop/Stock`). If these differ, a run persists to disk but never appears in history. Normally identical; Step 1b's config consolidation should make the backend pass an explicit `results_dir` through so the write and read paths cannot diverge.

Step 1a.6 (providers / diagnostics / pdf / diff endpoints) is now **complete** — see the Endpoints table above.
Still deferred to **Step 1b**: `webapp.py` → API-client migration.

## Rollback

The state immediately before Step 1a is preserved as both a tag and a branch named `pre-fastapi-refactor` (commit `b84edd6`). Because both refs share that name, use the explicit `refs/tags/` prefix to silence git's ambiguity warning:

    git reset --hard refs/tags/pre-fastapi-refactor

Or to inspect what changed:

    git diff refs/tags/pre-fastapi-refactor..HEAD -- backend/ tradingagents/graph/trading_graph.py tradingagents/storage/sqlite_history.py
