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

## Known limitations (to address before Step 1b)

Step 1a is intentionally scoped to "streaming spine + history read." Surfaced by the real-LLM smoke test and the final architectural review:

1. **Backend-initiated runs are not auto-indexed.** The engine's `_log_state` writes to `{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json`. `rebuild_from_disk` indexes `{ticker}/{date}/final_state_report.json` — which is produced by `webapp.py:save_analysis_results`, not the engine. Until Step 1b ports `save_analysis_results` into the backend, new API-initiated runs won't appear in `GET /api/history`.
2. **WS connect after a run is terminal hangs for 30 s.** The handler blocks on the empty queue until ping. There's no `is_terminal()` fast-path that replays the final state for late subscribers.
3. **Chunk-drain ordering only enforced on success.** On `aborted`/`error`, stragglers from `run_coroutine_threadsafe` can land after the terminal event. Window is tiny in practice (queue puts are near-instant) but real.
4. **`RunRegistry` has no eviction.** Completed handles stay in memory for the life of the process. Fine for local dev; add TTL/`drop()` before any shared deployment.
5. **`AbortResponse.status` reflects state at signal time, not after honored.** Cancel is async; the field is almost always `"running"`. Either drop it or rename it.
6. **History `set_rating` UPDATE matches zero rows silently** when the ticker/date isn't indexed — returns 200 with no DB change. Add a rowcount check + 404 before any production use.

None of these affect the engineering claim "Step 1a streaming + history works"; all are well-understood and tracked.

## Rollback

The state immediately before Step 1a is preserved as both a tag and a branch named `pre-fastapi-refactor` (commit `b84edd6`). Because both refs share that name, use the explicit `refs/tags/` prefix to silence git's ambiguity warning:

    git reset --hard refs/tags/pre-fastapi-refactor

Or to inspect what changed:

    git diff refs/tags/pre-fastapi-refactor..HEAD -- backend/ tradingagents/graph/trading_graph.py tradingagents/storage/sqlite_history.py
