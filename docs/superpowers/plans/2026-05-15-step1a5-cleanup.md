# Step 1a.5 — Backend Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 6 known limitations the Step 1a final review flagged as Step 1b prerequisites, so the FastAPI backend persists its own runs, behaves correctly for late WebSocket subscribers, and has honest API responses.

**Architecture:** Six focused, independent fixes. The largest (run persistence) adds a `backend/services/persistence.py` that mirrors `webapp.py:save_analysis_results` minus the PDF, writing `{results_dir}/{ticker}/{date}/final_state_report.json` and calling the existing `sqlite_history.index_one_analysis`. The rest are surgical edits to `runner.py`, `analysis.py`, `registry.py`, `history.py`, `schemas.py`, and `sqlite_history.py`. `webapp.py` and `cli/` remain untouched.

**Tech Stack:** FastAPI, pytest, pytest-asyncio, the existing `tradingagents` engine + `sqlite_history`. Python 3.10+.

**Scope boundary:** This plan covers ONLY the 6 limitations from `docs/backend.md`'s "Known limitations" section. **Deferred to Step 1a.6:** the `/api/providers/*`, `/api/diagnostics/*`, `GET /api/runs/{id}/pdf`, `GET /api/history/{id}/diff/{otherId}` endpoints. **Deferred to Step 1b:** `webapp.py` → API-client migration.

**Rollback:** `git reset --hard refs/tags/step-1a-backend-complete` reverts to the Step 1a milestone. The pre-everything point is still `refs/tags/pre-fastapi-refactor`.

---

## File Structure

```
backend/services/persistence.py    # NEW: write final_state_report.json + index it
backend/services/runner.py         # MODIFY: drain-on-all-paths + call persistence on success
backend/services/history.py        # MODIFY: set_rating returns bool, drop dead hasattr guard
backend/routes/analysis.py         # MODIFY: WS terminal fast-path + registry.drop on terminal
backend/routes/history.py          # MODIFY: 404 when set_rating matches no row
backend/schemas.py                 # MODIFY: AbortResponse {run_id, accepted} not {run_id, status}
tradingagents/storage/sqlite_history.py  # MODIFY: set_rating returns rows-affected bool

tests/backend/test_persistence.py       # NEW
tests/backend/test_runner.py            # MODIFY: assert drain on abort/error ordering
tests/backend/test_analysis_routes.py   # MODIFY: terminal fast-path + abort schema + eviction
tests/backend/test_history_routes.py    # MODIFY: 404 on unknown rating target
```

Each fix is one task with its own commit. **Tasks MUST be implemented in numbered order** — Task 2 restructures the same region of `runner.py` that Task 1 touches (see the cross-task note at the end).

---

## Task 1: Persist successful backend runs (Limitation #1)

Backend-initiated runs must write `{results_dir}/{ticker}/{date}/final_state_report.json` and index it, so `GET /api/history` reflects them. The `results_dir` MUST be the one the engine actually used (`graph.config["results_dir"]`), not `backend.config.Settings.results_dir` — they can differ (the engine reads `TRADINGAGENTS_RESULTS_DIR` / its own default; Settings defaults to `~/Desktop/Stock`).

**Files:**
- Create: `backend/services/persistence.py`
- Create: `tests/backend/test_persistence.py`
- Modify: `backend/services/runner.py`

- [ ] **Step 1: Write failing persistence test**

Create `tests/backend/test_persistence.py`:

```python
import json
from pathlib import Path

from backend.services.persistence import persist_run


def test_persist_run_writes_json_and_indexes(tmp_path: Path):
    final_state = {
        "company_of_interest": "TEST",
        "trade_date": "2026-01-01",
        "final_trade_decision": "BUY: strong",
        "market_report": "m",
        "messages": ["should-be-dropped"],
    }

    persist_run(
        results_dir=tmp_path,
        ticker="TEST",
        trade_date="2026-01-01",
        final_state=final_state,
        model="deepseek-chat",
        provider="DeepSeek",
    )

    json_file = tmp_path / "TEST" / "2026-01-01" / "final_state_report.json"
    assert json_file.exists()
    saved = json.loads(json_file.read_text())
    assert "messages" not in saved
    assert saved["final_trade_decision"] == "BUY: strong"

    from tradingagents.storage import sqlite_history

    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert rows and rows[0]["ticker"] == "TEST"
    assert rows[0]["json_path"] == str(json_file)


def test_persist_run_is_idempotent(tmp_path: Path):
    fs = {"company_of_interest": "TEST", "trade_date": "2026-01-01",
          "final_trade_decision": "HOLD"}
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    from tradingagents.storage import sqlite_history
    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert len(rows) == 1  # UPSERT, not duplicate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_persistence.py -v`
Expected: FAIL — `backend.services.persistence` does not exist.

- [ ] **Step 3: Implement persistence**

Create `backend/services/persistence.py`:

```python
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tradingagents.storage import sqlite_history

logger = logging.getLogger(__name__)


def persist_run(
    results_dir: Path | str,
    ticker: str,
    trade_date: str,
    final_state: dict[str, Any],
    model: str | None = None,
    provider: str | None = None,
) -> Path:
    """Write final_state_report.json and index it in sqlite_history.

    Mirrors webapp.py:save_analysis_results minus the PDF (PDF generation
    is deferred to Step 1a.6). Returns the JSON path written.
    """
    results_dir = Path(results_dir)
    save_path = results_dir / ticker / trade_date
    save_path.mkdir(parents=True, exist_ok=True)

    serializable = {k: v for k, v in final_state.items() if k != "messages"}
    json_path = save_path / "final_state_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=4)

    try:
        sqlite_history.index_one_analysis(
            results_dir,
            ticker=ticker,
            trade_date=trade_date,
            json_path=str(json_path),
            pdf_path=None,
            decision_text=final_state.get("final_trade_decision", ""),
            model=model,
            provider=provider,
            has_position=None,
        )
    except Exception:
        logger.exception("Failed to index analysis %s/%s", ticker, trade_date)

    return json_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_persistence.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Wire persistence into the runner**

In `backend/services/runner.py`, the `_run` function builds the graph inside `_sync_runner` and discards everything but `final_state`. We need the engine's resolved `results_dir`, `deep_think_llm`, and `llm_provider`.

The current `_sync_runner` is:

```python
    def _sync_runner() -> dict[str, Any]:
        graph = graph_factory(request.config_overrides)
        return graph.propagate(
            request.ticker,
            request.trade_date,
            on_chunk=_emit_chunk,
            cancel_event=handle.cancel_event,
        )
```

Change it to capture engine config via a closure dict (add the `engine_meta` dict just above the `_sync_runner` def):

```python
    engine_meta: dict[str, Any] = {}

    def _sync_runner() -> dict[str, Any]:
        graph = graph_factory(request.config_overrides)
        cfg = getattr(graph, "config", {}) or {}
        engine_meta["results_dir"] = cfg.get("results_dir")
        engine_meta["model"] = cfg.get("deep_think_llm")
        engine_meta["provider"] = cfg.get("llm_provider")
        return graph.propagate(
            request.ticker,
            request.trade_date,
            on_chunk=_emit_chunk,
            cancel_event=handle.cancel_event,
        )
```

The current success tail of `_run` is:

```python
    # Drain all in-flight chunk queue-puts before emitting "done", so consumers
    # always see chunks before the terminal event regardless of engine speed.
    if _chunk_futures:
        await asyncio.gather(
            *[asyncio.wrap_future(f) for f in _chunk_futures],
        )

    await handle.mark_done(final_state)
```

Change it to persist BEFORE `mark_done` (so a client reacting to `done` already sees the history row):

```python
    # Drain all in-flight chunk queue-puts before emitting "done", so consumers
    # always see chunks before the terminal event regardless of engine speed.
    if _chunk_futures:
        await asyncio.gather(
            *[asyncio.wrap_future(f) for f in _chunk_futures],
        )

    results_dir = engine_meta.get("results_dir")
    if results_dir:
        try:
            await asyncio.to_thread(
                persist_run,
                results_dir,
                request.ticker,
                request.trade_date,
                final_state,
                engine_meta.get("model"),
                engine_meta.get("provider"),
            )
        except Exception:
            logger.exception("Persist failed for %s", handle.run_id)

    await handle.mark_done(final_state)
```

Add this import near the other `from backend.services...` imports at the top of `runner.py`:

```python
from backend.services.persistence import persist_run
```

(Task 2 restructures this same tail. Implementing Task 1 then Task 2 in order is correct — Task 2's full replacement re-includes the persistence block.)

- [ ] **Step 6: Verify runner tests still pass**

Run: `pytest tests/backend/test_runner.py tests/backend/test_persistence.py -v`
Expected: PASS. The existing runner tests use a `_FakeGraph` with no `.config` attribute — `getattr(graph, "config", {})` yields `{}`, so `results_dir` is falsy and persistence is skipped. No runner-test changes needed in Task 1.

- [ ] **Step 7: Commit**

```bash
git add backend/services/persistence.py tests/backend/test_persistence.py backend/services/runner.py
git commit -m "feat(backend): persist + index successful runs (Limitation #1)"
```

---

## Task 2: Drain chunk futures on abort/error paths (Limitation #3)

The `_chunk_futures` drain currently runs only on the success path. On abort/error, stragglers scheduled via `run_coroutine_threadsafe` can land in the queue AFTER the terminal event. Make the drain happen before every terminal transition.

**Files:**
- Modify: `backend/services/runner.py`
- Modify: `tests/backend/test_runner.py`

- [ ] **Step 1: Write a failing ordering test**

Add to `tests/backend/test_runner.py`:

```python
@pytest.mark.asyncio
async def test_abort_drains_chunks_before_aborted_event():
    """On abort, every chunk emitted before cancellation must appear in the
    queue BEFORE the 'aborted' terminal event."""
    registry = RunRegistry()

    class _SlowCancelGraph:
        def propagate(self, company_name, trade_date, on_chunk=None, cancel_event=None):
            for i in range(5):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Analysis cancelled by caller")
                if on_chunk is not None:
                    on_chunk({"market_report": f"c-{i}"})
            raise RuntimeError("Analysis cancelled by caller")

    req = AnalysisRequest(ticker="TEST", trade_date="2026-01-01")
    handle = await start_analysis(req, registry, graph_factory=lambda cfg: _SlowCancelGraph())
    handle.cancel_event.set()
    await asyncio.wait_for(handle.task, timeout=2.0)

    events = []
    while not handle.queue.empty():
        events.append(handle.queue.get_nowait())

    types = [e["type"] for e in events]
    assert types[-1] == "aborted"
    aborted_idx = types.index("aborted")
    assert "chunk" not in types[aborted_idx + 1:]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_runner.py::test_abort_drains_chunks_before_aborted_event -v`
Expected: FAIL — chunk events appear after `aborted` because the abort path skips the drain. If it passes by timing luck, run it 5× (`for i in 1 2 3 4 5; do pytest ...::test_abort_drains_chunks_before_aborted_event -q; done`). If it cannot be made to fail reliably, note that in the commit message and proceed — the fix is still correct.

- [ ] **Step 3: Extract a `_drain` helper and call it on every terminal path**

In `backend/services/runner.py`, replace the body of `_run` from the `try:` (the `final_state = await asyncio.to_thread(_sync_runner)` line) to the end of the function with:

```python
    async def _drain() -> None:
        if _chunk_futures:
            await asyncio.gather(
                *[asyncio.wrap_future(f) for f in _chunk_futures],
                return_exceptions=True,
            )

    try:
        final_state = await asyncio.to_thread(_sync_runner)
    except RuntimeError as exc:
        await _drain()
        if "cancelled" in str(exc).lower():
            await handle.mark_aborted()
            return
        logger.exception("Analysis %s failed", handle.run_id)
        await handle.mark_error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - surface every engine failure
        await _drain()
        logger.exception("Analysis %s failed", handle.run_id)
        await handle.mark_error(str(exc))
        return

    await _drain()

    results_dir = engine_meta.get("results_dir")
    if results_dir:
        try:
            await asyncio.to_thread(
                persist_run,
                results_dir,
                request.ticker,
                request.trade_date,
                final_state,
                engine_meta.get("model"),
                engine_meta.get("provider"),
            )
        except Exception:
            logger.exception("Persist failed for %s", handle.run_id)

    await handle.mark_done(final_state)
```

This removes the old `if _chunk_futures: await asyncio.gather(...)` block (now inside `_drain`) and guarantees the drain precedes `mark_aborted`, `mark_error`, and `mark_done`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_runner.py -v`
Expected: PASS (all — the new ordering test plus the existing 4).

- [ ] **Step 5: Commit**

```bash
git add backend/services/runner.py tests/backend/test_runner.py
git commit -m "fix(backend): drain chunk futures before every terminal event (Limitation #3)"
```

---

## Task 3: WebSocket terminal fast-path (Limitation #2)

If a client connects to `/api/analysis/ws/{run_id}` after the run is already terminal, the handler blocks on the empty queue for 30 s before pinging. Add a fast-path: if the handle is terminal at connect time, emit one synthetic terminal event and close.

**Files:**
- Modify: `backend/routes/analysis.py`
- Modify: `tests/backend/test_analysis_routes.py`

- [ ] **Step 1: Write a failing test**

Add to `tests/backend/test_analysis_routes.py`:

```python
def test_websocket_after_run_terminal_returns_immediately(app_with_fake_graph):
    import time
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app_with_fake_graph) as client:
        resp = client.post(
            "/api/analysis/start",
            json={"ticker": "TEST", "trade_date": "2026-01-01"},
        )
        run_id = resp.json()["run_id"]

        with client.websocket_connect(f"/api/analysis/ws/{run_id}") as ws:
            while True:
                if json.loads(ws.receive_text())["type"] == "done":
                    break

        # Second connect AFTER terminal must resolve fast: either a terminal
        # event, or 4404 if the handle was already evicted (Task 4). Never a
        # ~30s hang.
        start = time.monotonic()
        try:
            with client.websocket_connect(f"/api/analysis/ws/{run_id}") as ws2:
                msg = json.loads(ws2.receive_text())
                assert msg["type"] in {"done", "aborted", "error"}
        except WebSocketDisconnect as exc:
            assert exc.code == 4404
        elapsed = time.monotonic() - start
        assert elapsed < 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_analysis_routes.py::test_websocket_after_run_terminal_returns_immediately -v`
Expected: FAIL — second connect blocks ~30 s; the `elapsed < 5.0` assertion fails (or the test times out).

- [ ] **Step 3: Add the fast-path**

In `backend/routes/analysis.py`, the `stream` handler currently is:

```python
@router.websocket("/ws/{run_id}")
async def stream(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    registry: RunRegistry = websocket.app.state.registry
    handle = registry.get(run_id)
    if handle is None:
        await websocket.close(code=4404)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(handle.queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            await websocket.send_text(json.dumps(event, default=str))
            if event["type"] in {"done", "aborted", "error"}:
                break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
```

Insert a terminal fast-path immediately after the `handle is None` check and BEFORE the `try:` loop:

```python
    if handle.is_terminal():
        payload: dict = {"type": handle.status.value}
        if handle.status.value == "error" and handle.error:
            payload["message"] = handle.error
        await websocket.send_text(json.dumps(payload, default=str))
        await websocket.close()
        return
```

Because this `return` is BEFORE the `try:`, it does NOT trigger the `finally:` block — important for the Task 4 interaction (the fast-path must not evict).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/test_analysis_routes.py -v`
Expected: PASS (all — the new test plus the original 5/6). Run twice to confirm no flake.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/analysis.py tests/backend/test_analysis_routes.py
git commit -m "feat(backend): WebSocket terminal fast-path for late subscribers (Limitation #2)"
```

---

## Task 4: RunRegistry eviction on terminal (Limitation #4)

Completed handles stay in `RunRegistry._handles` forever. Drop a handle once a WS consumer that ran the live queue loop has seen its terminal event AND the run is terminal. The Task 3 fast-path deliberately does NOT evict (its `return` precedes the `try/finally`), so the first live-loop consumer evicts and any later connect gets a fast 4404 — both outcomes are covered by Task 3's test.

**Files:**
- Modify: `backend/routes/analysis.py`
- Modify: `tests/backend/test_analysis_routes.py`

- [ ] **Step 1: Write a failing test**

Add to `tests/backend/test_analysis_routes.py`:

```python
def test_registry_drops_handle_after_terminal_ws(app_with_fake_graph):
    with TestClient(app_with_fake_graph) as client:
        resp = client.post(
            "/api/analysis/start",
            json={"ticker": "TEST", "trade_date": "2026-01-01"},
        )
        run_id = resp.json()["run_id"]

        with client.websocket_connect(f"/api/analysis/ws/{run_id}") as ws:
            while True:
                if json.loads(ws.receive_text())["type"] == "done":
                    break

    registry = app_with_fake_graph.state.registry
    assert registry.get(run_id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_analysis_routes.py::test_registry_drops_handle_after_terminal_ws -v`
Expected: FAIL — `registry.get(run_id)` still returns the handle (never dropped).

- [ ] **Step 3: Evict in the WS `finally`**

In `backend/routes/analysis.py`, the `finally` block of `stream` currently is:

```python
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
```

Change it to evict when the run is terminal (so a client disconnecting mid-run does NOT orphan a live handle):

```python
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        # Best-effort eviction: only drop once the run itself is terminal,
        # so a client disconnecting mid-run does not remove a live handle.
        # Caveat: with multiple concurrent WS subscribers the first to finish
        # evicts the handle for the rest — acceptable under the Step 1a
        # single-user model.
        if handle is not None and handle.is_terminal():
            registry.drop(run_id)
```

`registry` and `handle` are already bound earlier in the handler. The Task 3 fast-path returns before the `try:`, so it never reaches this `finally` — confirmed by reading the code after applying Task 3.

- [ ] **Step 4: Run the full analysis-routes suite (Task 3 + Task 4 must coexist)**

Run: `pytest tests/backend/test_analysis_routes.py -v` (run twice to rule out flake)
Expected: PASS (all). Specifically:
- `test_registry_drops_handle_after_terminal_ws` passes (handle evicted after `done`).
- `test_websocket_after_run_terminal_returns_immediately` (Task 3) passes via its `WebSocketDisconnect`/4404 branch, because the first connection's `finally` evicted the handle, so the second connect hits `handle is None` → `close(4404)`. The test already tolerates both outcomes.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/analysis.py tests/backend/test_analysis_routes.py
git commit -m "fix(backend): evict terminal run handles from registry (Limitation #4)"
```

---

## Task 5: Honest AbortResponse (Limitation #5)

`AbortResponse.status` returns `handle.status.value`, almost always `"running"` because cancellation is asynchronous — it misleads callers into thinking the abort completed. Replace with `accepted: bool`. Also add the missing unknown-run_id abort test (Step 1a Minor coverage gap).

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/routes/analysis.py`
- Modify: `tests/backend/test_analysis_routes.py`

- [ ] **Step 1: Add/adjust failing tests**

In `tests/backend/test_analysis_routes.py`, locate `test_abort_transitions_run_to_aborted`. After its `abort = client.post(f"/api/analysis/{run_id}/abort")` and `assert abort.status_code == 200`, add:

```python
        body = abort.json()
        assert body == {"run_id": run_id, "accepted": True}
```

Add a new test for the unknown-run_id path:

```python
def test_abort_unknown_run_id_returns_404(app_with_fake_graph):
    with TestClient(app_with_fake_graph) as client:
        resp = client.post("/api/analysis/NOPE/abort")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/test_analysis_routes.py::test_abort_transitions_run_to_aborted tests/backend/test_analysis_routes.py::test_abort_unknown_run_id_returns_404 -v`
Expected: the body assertion FAILS — current response is `{"run_id":..., "status":"running"}`, not `{"run_id":..., "accepted":true}`. (The 404 test may already pass — the `handle is None` → `HTTPException(404)` branch exists. That's fine; it formalizes coverage.)

- [ ] **Step 3: Change the schema**

In `backend/schemas.py`, replace:

```python
class AbortResponse(BaseModel):
    run_id: str
    status: str
```

with:

```python
class AbortResponse(BaseModel):
    run_id: str
    accepted: bool
```

- [ ] **Step 4: Update the abort route**

In `backend/routes/analysis.py`, the `abort` handler ends with:

```python
    handle.cancel_event.set()
    return AbortResponse(run_id=run_id, status=handle.status.value)
```

Change to:

```python
    handle.cancel_event.set()
    return AbortResponse(run_id=run_id, accepted=True)
```

The `handle is None` → `raise HTTPException(status_code=404, detail="run_id not found")` branch above is unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/backend/test_analysis_routes.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/routes/analysis.py tests/backend/test_analysis_routes.py
git commit -m "fix(backend): AbortResponse returns accepted bool not misleading status (Limitation #5)"
```

---

## Task 6: set_rating 404 on unknown target (Limitation #6)

`sqlite_history.set_rating` runs an UPDATE that silently matches zero rows when the ticker/date isn't indexed; the API returns `200 {"updated": true}` — a lie. Make `set_rating` report rows-affected, propagate it, and return 404. Also remove the now-dead `hasattr` guard + unreachable 501 path (Step 1a review Minor).

**Files:**
- Modify: `tradingagents/storage/sqlite_history.py`
- Modify: `backend/services/history.py`
- Modify: `backend/routes/history.py`
- Modify: `tests/backend/test_history_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/test_history_routes.py`:

```python
def test_patch_history_unknown_target_returns_404(seeded_results):
    with _client() as client:
        resp = client.patch(
            "/api/history/GHOST/2099-01-01",
            json={"rating": "good"},
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_history_routes.py::test_patch_history_unknown_target_returns_404 -v`
Expected: FAIL — currently returns 200 `{"updated": true}` even though no row matched.

- [ ] **Step 3: Make `sqlite_history.set_rating` return rows-affected**

In `tradingagents/storage/sqlite_history.py`, the current `set_rating` is:

```python
def set_rating(results_dir: Path | str, ticker: str, trade_date: str, rating: str) -> None:
    """Set a user-supplied rating on a stored analysis.

    Distinct from the auto-extracted `rating` column (populated from the
    analysis text by `_extract_rating`); this is for the end user's own
    rating, e.g., "good", "bad", "needs-revision".
    """
    results_dir = Path(results_dir)
    with _connect(results_dir) as conn:
        _init_schema(conn)
        conn.execute(
            "UPDATE analyses SET user_rating = ? WHERE ticker = ? AND trade_date = ?",
            (rating, ticker, trade_date),
        )
```

Change the return type to `bool`:

```python
def set_rating(results_dir: Path | str, ticker: str, trade_date: str, rating: str) -> bool:
    """Set a user-supplied rating on a stored analysis.

    Distinct from the auto-extracted `rating` column (populated from the
    analysis text by `_extract_rating`); this is for the end user's own
    rating, e.g., "good", "bad", "needs-revision".

    Returns True if a matching row was updated, False if no analysis with
    that ticker+trade_date is indexed.
    """
    results_dir = Path(results_dir)
    with _connect(results_dir) as conn:
        _init_schema(conn)
        cur = conn.execute(
            "UPDATE analyses SET user_rating = ? WHERE ticker = ? AND trade_date = ?",
            (rating, ticker, trade_date),
        )
        return cur.rowcount > 0
```

- [ ] **Step 4: Simplify the service wrapper**

In `backend/services/history.py`, the current `set_rating` is:

```python
def set_rating(results_dir: Path, ticker: str, trade_date: str, rating: str) -> None:
    if hasattr(sqlite_history, "set_rating"):
        sqlite_history.set_rating(results_dir, ticker, trade_date, rating)
    else:
        raise NotImplementedError("set_rating not yet supported by sqlite_history")
```

Replace with a direct call returning the bool:

```python
def set_rating(results_dir: Path, ticker: str, trade_date: str, rating: str) -> bool:
    return sqlite_history.set_rating(results_dir, ticker, trade_date, rating)
```

- [ ] **Step 5: Return 404 from the route**

In `backend/routes/history.py`, the current `patch_history` is:

```python
@router.patch("/{ticker}/{trade_date}")
def patch_history(ticker: str, trade_date: str, body: PatchHistoryRequest) -> dict:
    settings = get_settings_dep()
    if body.note is not None:
        history_service.set_note(settings.results_dir, ticker, trade_date, body.note)
    if body.rating is not None:
        try:
            history_service.set_rating(settings.results_dir, ticker, trade_date, body.rating)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
    return {"ticker": ticker, "trade_date": trade_date, "updated": True}
```

Replace with:

```python
@router.patch("/{ticker}/{trade_date}")
def patch_history(ticker: str, trade_date: str, body: PatchHistoryRequest) -> dict:
    settings = get_settings_dep()
    if body.note is not None:
        history_service.set_note(settings.results_dir, ticker, trade_date, body.note)
    if body.rating is not None:
        updated = history_service.set_rating(
            settings.results_dir, ticker, trade_date, body.rating
        )
        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"No indexed analysis for {ticker} {trade_date}",
            )
    return {"ticker": ticker, "trade_date": trade_date, "updated": True}
```

`HTTPException` is already imported in this file.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/backend/test_history_routes.py -v`
Expected: PASS (all — the new 404 test plus the existing `test_patch_history_sets_rating`, which patches an EXISTING seeded record so still gets 200 + the read-back assertion).

- [ ] **Step 7: Confirm no other caller relied on the old return type**

Run: `grep -rn "set_rating" /Users/tonniclaw/TradingAgents-WebUI --include="*.py" | grep -v "/test"`
Expected: only `backend/services/history.py` and `tradingagents/storage/sqlite_history.py`. `webapp.py` predates the helper and does not call it. A caller that ignored the old `None` is unaffected by a new `bool`.

Run: `pytest tests/ --ignore=tests/backend -q --no-header`
Expected: same 6 pre-existing failures, no new ones.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/storage/sqlite_history.py backend/services/history.py backend/routes/history.py tests/backend/test_history_routes.py
git commit -m "fix(backend): 404 when rating a non-indexed analysis; drop dead guard (Limitation #6)"
```

---

## Task 7: Final verification + close-out

- [ ] **Step 1: Full backend suite**

Run via the watchdog idiom:

```bash
pytest tests/backend/ -v > /tmp/o.log 2>&1 &
P=$!; for i in {1..60}; do kill -0 $P 2>/dev/null || break; sleep 1; done; kill -9 $P 2>/dev/null; wait $P 2>/dev/null
tail -30 /tmp/o.log
```

Expected: ALL backend tests pass (original 19 + the new ones from Tasks 1-6).

- [ ] **Step 2: No regression in existing tests**

Run: `pytest tests/ --ignore=tests/backend -q --no-header`
Expected: exactly the 6 known pre-existing failures (`test_env_overrides.py` ×2, `test_memory_log.py` ×2, `test_structured_agents.py` ×2). NO new failures.

- [ ] **Step 3: Streamlit still launches**

Start `streamlit run webapp.py --server.headless true --server.port 8503` in the background ~8s, confirm "You can now view your Streamlit app" in its log, then kill it. Expected: no import/engine errors from the `set_rating` signature change.

- [ ] **Step 4: Update docs/backend.md**

In `docs/backend.md`, replace the entire "## Known limitations (to address before Step 1b)" section (heading + intro + the 6-item list + the closing line) with:

```markdown
## Resolved in Step 1a.5

The 6 limitations the Step 1a review flagged are now fixed:

1. ✅ Backend runs persist `{ticker}/{date}/final_state_report.json` and are indexed (`backend/services/persistence.py`).
2. ✅ WS connect after a terminal run returns a synthetic terminal event immediately (no 30s hang).
3. ✅ Chunk-future drain runs before every terminal event (success/abort/error).
4. ✅ `RunRegistry` evicts terminal handles when their WS consumer finishes.
5. ✅ `POST /abort` returns `{run_id, accepted}` instead of a misleading `status`.
6. ✅ `PATCH /api/history/...` returns 404 when the analysis isn't indexed.

Still deferred to **Step 1a.6**: `/api/providers/*`, `/api/diagnostics/*`, `GET /api/runs/{id}/pdf`, `GET /api/history/{id}/diff/{otherId}`.
Still deferred to **Step 1b**: `webapp.py` → API-client migration.
```

Also update the endpoint table row for abort: change its Notes cell to mention it returns `{run_id, accepted}`.

- [ ] **Step 5: Commit + tag**

```bash
git add docs/backend.md
git commit -m "docs(backend): mark Step 1a.5 limitations resolved"
git tag -a step-1a5-cleanup-complete -m "Step 1a.5 — 6 known limitations fixed; Step 1b unblocked"
```

- [ ] **Step 6: Report the commit range**

Run: `git log --oneline refs/tags/step-1a-backend-complete..HEAD`
Expected: 7 commits (Tasks 1-6 + the docs commit), all on `main`.

---

## Self-Review (plan author)

**Spec coverage:** All 6 limitations from `docs/backend.md` → Tasks 1-6 respectively. Step 1a Minor coverage gaps (abort 404 test, dead `hasattr`, unreachable 501) folded into Tasks 5 and 6. Final verification + docs + tag in Task 7. No gaps.

**Placeholder scan:** No TBD/TODO/"similar to Task N". Every code step shows full before/after with exact paths. The Task 3↔Task 4 interaction is resolved inline (fast-path `return` precedes `try/finally`, so it never evicts; Task 3's test tolerates both terminal-event and 4404 outcomes).

**Type consistency:**
- `persist_run(results_dir, ticker, trade_date, final_state, model=None, provider=None) -> Path` — defined Task 1 Step 3, called identically Task 1 Step 5 and Task 2 Step 3.
- `set_rating -> bool` — consistent across `sqlite_history` (Task 6 Step 3), `history` service (Step 4), route consumes `updated` bool (Step 5), tests (Step 1).
- `AbortResponse{run_id: str, accepted: bool}` — schema (Task 5 Step 3) ↔ route (Step 4) ↔ test (Step 1).
- `_drain()` — defined once (Task 2 Step 3), referenced only within that replacement block.
- `engine_meta` dict keys (`results_dir`, `model`, `provider`) — set in Task 1 Step 5's `_sync_runner`, read in Task 1's tail and Task 2's replacement identically.

**Cross-task ordering risk:** Task 1 adds a success-path persistence block; Task 2 fully replaces the `try:`→end region (re-including persistence). Numbered order (1→2→…→7) is mandatory and is stated at the top of the File Structure section and in Task 1 Step 5. Executing in order is conflict-free.
