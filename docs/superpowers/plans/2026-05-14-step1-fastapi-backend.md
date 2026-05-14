# Step 1a — FastAPI Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a `backend/` FastAPI service that wraps the existing `tradingagents/` engine and exposes streaming analysis + history endpoints, with full pytest coverage, while leaving `webapp.py` and `cli/` untouched.

**Architecture:** A thin async FastAPI layer registers HTTP/WS routes that delegate to a `RunRegistry` (in-memory `{run_id → RunHandle}`). Each analysis runs in `asyncio.to_thread` calling the existing `TradingAgentsGraph.propagate()`, which is extended with one new optional callback (`on_chunk`) and one cancel signal (`cancel_event`) — both default-None so the CLI and Streamlit paths are byte-identical. Streaming chunks flow back through an `asyncio.Queue` consumed by the WebSocket handler. History endpoints are CRUD wrappers around the existing `tradingagents.storage.sqlite_history`.

**Tech Stack:** FastAPI, uvicorn[standard], starlette WebSockets, pydantic v2, pytest, pytest-asyncio, httpx (test client). Python 3.10+.

**Scope boundary:** This plan covers Step 1a only — streaming analysis + history. **Deferred to Step 1a.5:** `/api/providers/*`, `/api/diagnostics/*`, `/api/runs/{id}/pdf`, `/api/history/{id}/diff/{otherId}`. **Deferred to Step 1b:** migrating `webapp.py` to consume the API instead of importing `tradingagents/` directly.

**Rollback:** `git reset --hard pre-fastapi-refactor` (tag) or `git checkout pre-fastapi-refactor` (branch) at any time restores commit `b84edd6`.

---

## File Structure

```
backend/
├── __init__.py
├── main.py                      # FastAPI app factory, CORS, router includes
├── config.py                    # Settings (results_dir, host, port, cors_origins)
├── deps.py                      # FastAPI dependencies (settings, registry singleton)
├── schemas.py                   # Pydantic request/response models
├── services/
│   ├── __init__.py
│   ├── registry.py              # RunRegistry + RunHandle dataclass
│   ├── runner.py                # async wrapper around TradingAgentsGraph
│   └── history.py               # wraps sqlite_history
└── routes/
    ├── __init__.py
    ├── health.py                # GET /api/health
    ├── analysis.py              # POST /start, WS /ws/{id}, POST /{id}/abort
    └── history.py               # GET /history, PATCH /history/{id}

tests/backend/
├── __init__.py
├── conftest.py                  # FastAPI TestClient + fake graph fixture
├── test_health.py
├── test_registry.py
├── test_runner.py
├── test_engine_hook.py
├── test_analysis_routes.py
└── test_history_routes.py

tradingagents/graph/trading_graph.py   # MODIFIED: add on_chunk + cancel_event params
tradingagents/storage/sqlite_history.py # MAYBE MODIFIED: add user_rating column if absent
pyproject.toml                          # MODIFIED: add fastapi/uvicorn/httpx/pytest-asyncio
docs/backend.md                         # NEW: how to run + test + roll back
```

Each `backend/routes/*.py` is one router, ~50 lines. `services/runner.py` is the only file with non-trivial concurrency — it owns the to_thread + queue glue and is unit-tested with a fake graph.

---

## Task 1: Project scaffold + health endpoint

**Files:**
- Create: `backend/__init__.py`, `backend/main.py`, `backend/config.py`, `backend/deps.py`, `backend/routes/__init__.py`, `backend/routes/health.py`
- Modify: `pyproject.toml` (add dependencies)
- Create: `tests/backend/__init__.py`, `tests/backend/conftest.py`, `tests/backend/test_health.py`

- [ ] **Step 1: Add backend dependencies to pyproject.toml**

In `pyproject.toml`, append these to `dependencies` (keep existing order, add at end before closing bracket):

```toml
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "pytest-asyncio>=0.24.0",
    "pydantic-settings>=2.0.0",
```

Also update `[tool.setuptools.packages.find]`:

```toml
include = ["tradingagents*", "cli*", "backend*"]
```

And under `[tool.pytest.ini_options]`, add:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -e .`
Expected: installs fastapi, uvicorn, httpx, pytest-asyncio, pydantic-settings without conflicts.

- [ ] **Step 3: Write failing health test**

Create `tests/backend/__init__.py` (empty file).

Create `tests/backend/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)
```

Create `tests/backend/test_health.py`:

```python
def test_health_returns_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/backend/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend'`.

- [ ] **Step 5: Create config + deps + health route + main app**

Create `backend/__init__.py` (empty file).

Create `backend/config.py`:

```python
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    results_dir: Path = Field(
        default=Path.home() / "Desktop" / "Stock",
        description="Where analysis results + sqlite history live.",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed origins for the future React dev server.",
    )

    model_config = SettingsConfigDict(
        env_prefix="TRADINGAGENTS_",
        env_file=".env",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
```

Create `backend/deps.py`:

```python
from fastapi import Request

from backend.config import Settings, get_settings
from backend.services.registry import RunRegistry


def settings_singleton() -> Settings:
    return get_settings()


def get_registry(request: Request) -> RunRegistry:
    return request.app.state.registry
```

(Note: `RunRegistry` is implemented in Task 3. Task 1 will leave the import in place but the registry won't be attached until Task 3. Until then, only the health route is registered, so `deps.get_registry` is never called.)

Create `backend/routes/__init__.py` (empty).

Create `backend/routes/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create `backend/services/__init__.py` (empty placeholder for Task 3).

Create `backend/services/registry.py` as a minimal stub (Task 3 will expand it):

```python
class RunRegistry:
    """Placeholder; real implementation lands in Task 3."""
```

Create `backend/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.deps import settings_singleton
from backend.routes import health


def create_app() -> FastAPI:
    settings = settings_singleton()
    app = FastAPI(title="TradingAgents Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/backend/test_health.py -v`
Expected: PASS.

- [ ] **Step 7: Smoke-run the server**

Run: `uvicorn backend.main:app --port 8765`
In another shell: `curl http://localhost:8765/api/health`
Expected: `{"status":"ok"}`.
Stop the server with Ctrl-C.

- [ ] **Step 8: Commit**

```bash
git add backend/ tests/backend/ pyproject.toml
git commit -m "feat(backend): scaffold FastAPI app with health endpoint"
```

---

## Task 2: Engine streaming hook (on_chunk + cancel_event)

The current `TradingAgentsGraph._run_graph()` consumes `self.graph.stream(...)` in `debug` mode only and discards chunks otherwise. Backend streaming requires consistent per-chunk emission regardless of `debug`. We add two optional parameters that preserve every existing call site.

**Files:**
- Modify: `tradingagents/graph/trading_graph.py:296-385` (`propagate` + `_run_graph`)
- Create: `tests/backend/test_engine_hook.py`

- [ ] **Step 1: Write failing test for the new callback**

Create `tests/backend/test_engine_hook.py`:

```python
import threading
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_run_graph_invokes_on_chunk_for_each_stream_chunk():
    """on_chunk must be called once per chunk yielded by graph.stream."""
    fake_chunks = [
        {"messages": [], "market_report": "draft-1"},
        {"messages": [], "market_report": "draft-2", "final_trade_decision": "BUY"},
    ]
    received: list[dict] = []
    cancel_event = threading.Event()

    instance = MagicMock(spec=TradingAgentsGraph)
    instance.graph = MagicMock()
    instance.graph.stream = MagicMock(return_value=iter(fake_chunks))
    instance.graph.invoke = MagicMock(return_value=fake_chunks[-1])
    instance.config = {"checkpoint_enabled": False}
    instance.propagator = MagicMock()
    instance.propagator.create_initial_state = MagicMock(return_value={})
    instance.propagator.get_graph_args = MagicMock(return_value={})
    instance.memory_log = MagicMock()
    instance.memory_log.get_past_context = MagicMock(return_value="")
    instance._log_state = MagicMock()
    instance.debug = False

    TradingAgentsGraph._run_graph(
        instance,
        "TEST",
        "2026-01-01",
        on_chunk=received.append,
        cancel_event=cancel_event,
    )

    assert len(received) == 2
    assert received[0]["market_report"] == "draft-1"
    assert received[1]["final_trade_decision"] == "BUY"


def test_run_graph_stops_when_cancel_event_set():
    """If cancel_event is set mid-stream, the loop must raise RuntimeError('cancelled')."""
    fake_chunks = [
        {"messages": [], "market_report": "draft-1"},
        {"messages": [], "market_report": "draft-2"},
        {"messages": [], "market_report": "draft-3"},
    ]
    cancel_event = threading.Event()
    received: list[dict] = []

    def on_chunk(chunk):
        received.append(chunk)
        if len(received) == 1:
            cancel_event.set()

    instance = MagicMock(spec=TradingAgentsGraph)
    instance.graph = MagicMock()
    instance.graph.stream = MagicMock(return_value=iter(fake_chunks))
    instance.config = {"checkpoint_enabled": False}
    instance.propagator = MagicMock()
    instance.propagator.create_initial_state = MagicMock(return_value={})
    instance.propagator.get_graph_args = MagicMock(return_value={})
    instance.memory_log = MagicMock()
    instance.memory_log.get_past_context = MagicMock(return_value="")
    instance._log_state = MagicMock()
    instance.debug = False

    with pytest.raises(RuntimeError, match="cancelled"):
        TradingAgentsGraph._run_graph(
            instance,
            "TEST",
            "2026-01-01",
            on_chunk=on_chunk,
            cancel_event=cancel_event,
        )

    assert len(received) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_engine_hook.py -v`
Expected: FAIL — `_run_graph` doesn't accept `on_chunk` or `cancel_event`.

- [ ] **Step 3: Modify _run_graph and propagate to accept the new params**

In `tradingagents/graph/trading_graph.py`, change the `propagate` signature (line 296) to:

```python
    def propagate(
        self,
        company_name,
        trade_date,
        on_chunk=None,
        cancel_event=None,
    ):
```

Inside `propagate`, replace the existing `return self._run_graph(company_name, trade_date)` (line 327) with:

```python
            return self._run_graph(
                company_name,
                trade_date,
                on_chunk=on_chunk,
                cancel_event=cancel_event,
            )
```

Change the `_run_graph` signature (line 334) to:

```python
    def _run_graph(
        self,
        company_name,
        trade_date,
        on_chunk=None,
        cancel_event=None,
    ):
```

Then replace the streaming/invoke block (the existing `if self.debug: ... else: ...` at lines 352-366) with:

```python
        # If a streaming callback is provided we always stream so the caller sees
        # every per-node delta — this matches what the existing `debug` branch did
        # but no longer requires `self.debug = True`.
        if on_chunk is not None or self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Analysis cancelled by caller")
                if on_chunk is not None:
                    on_chunk(chunk)
                if self.debug and chunk.get("messages"):
                    chunk["messages"][-1].pretty_print()
                trace.append(chunk)
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(init_agent_state, **args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_engine_hook.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run existing engine tests to confirm no regression**

Run: `pytest tests/ -v --ignore=tests/backend -x`
Expected: All existing tests still pass (the `on_chunk=None` path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/trading_graph.py tests/backend/test_engine_hook.py
git commit -m "feat(engine): add on_chunk + cancel_event hooks to TradingAgentsGraph.propagate"
```

---

## Task 3: RunRegistry + RunHandle

**Files:**
- Modify: `backend/services/registry.py` (replace stub with real implementation)
- Create: `tests/backend/test_registry.py`

- [ ] **Step 1: Write failing registry test**

Create `tests/backend/test_registry.py`:

```python
import asyncio

import pytest

from backend.services.registry import RunRegistry, RunStatus


@pytest.mark.asyncio
async def test_register_returns_unique_run_id():
    registry = RunRegistry()
    handle1 = registry.register()
    handle2 = registry.register()
    assert handle1.run_id != handle2.run_id
    assert handle1.status == RunStatus.PENDING


@pytest.mark.asyncio
async def test_get_returns_registered_handle():
    registry = RunRegistry()
    handle = registry.register()
    assert registry.get(handle.run_id) is handle


def test_get_unknown_run_id_returns_none():
    registry = RunRegistry()
    assert registry.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_handle_emit_queue_receives_event():
    registry = RunRegistry()
    handle = registry.register()
    await handle.emit({"type": "log", "msg": "hello"})
    event = await asyncio.wait_for(handle.queue.get(), timeout=0.5)
    assert event == {"type": "log", "msg": "hello"}


@pytest.mark.asyncio
async def test_mark_done_sets_status_and_emits_sentinel():
    registry = RunRegistry()
    handle = registry.register()
    await handle.mark_done(final_state={"final_trade_decision": "BUY"})
    assert handle.status == RunStatus.DONE
    assert handle.final_state == {"final_trade_decision": "BUY"}
    event = await asyncio.wait_for(handle.queue.get(), timeout=0.5)
    assert event["type"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_registry.py -v`
Expected: FAIL — `RunStatus` doesn't exist; `register()` doesn't return a handle.

- [ ] **Step 3: Implement the registry**

Replace `backend/services/registry.py` with:

```python
from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class RunHandle:
    run_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: RunStatus = RunStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    final_state: dict[str, Any] | None = None
    error: str | None = None
    task: asyncio.Task | None = None

    async def emit(self, event: dict[str, Any]) -> None:
        await self.queue.put(event)

    async def mark_running(self) -> None:
        self.status = RunStatus.RUNNING
        await self.emit({"type": "status", "status": "running"})

    async def mark_done(self, final_state: dict[str, Any]) -> None:
        self.status = RunStatus.DONE
        self.final_state = final_state
        await self.emit({"type": "done", "status": "done"})

    async def mark_error(self, message: str) -> None:
        self.status = RunStatus.ERROR
        self.error = message
        await self.emit({"type": "error", "message": message})

    async def mark_aborted(self) -> None:
        self.status = RunStatus.ABORTED
        await self.emit({"type": "aborted"})

    def is_terminal(self) -> bool:
        return self.status in {RunStatus.DONE, RunStatus.ABORTED, RunStatus.ERROR}


class RunRegistry:
    def __init__(self) -> None:
        self._handles: dict[str, RunHandle] = {}

    def register(self) -> RunHandle:
        run_id = uuid.uuid4().hex[:12]
        handle = RunHandle(run_id=run_id)
        self._handles[run_id] = handle
        return handle

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

    def drop(self, run_id: str) -> None:
        self._handles.pop(run_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_registry.py -v`
Expected: PASS (all five).

- [ ] **Step 5: Commit**

```bash
git add backend/services/registry.py tests/backend/test_registry.py
git commit -m "feat(backend): add RunRegistry + RunHandle for analysis lifecycle"
```

---

## Task 4: Runner service (async wrapper around the engine)

**Files:**
- Create: `backend/services/runner.py`
- Create: `tests/backend/test_runner.py`

- [ ] **Step 1: Write failing runner test using a fake graph**

Create `tests/backend/test_runner.py`:

```python
import asyncio

import pytest

from backend.services.registry import RunRegistry, RunStatus
from backend.services.runner import AnalysisRequest, start_analysis


class _FakeGraph:
    def __init__(self, chunks):
        self._chunks = chunks
        self.last_call = None

    def propagate(self, company_name, trade_date, on_chunk=None, cancel_event=None):
        self.last_call = (company_name, trade_date)
        for chunk in self._chunks:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Analysis cancelled by caller")
            if on_chunk is not None:
                on_chunk(chunk)
        final = {}
        for c in self._chunks:
            final.update(c)
        return final


@pytest.mark.asyncio
async def test_start_analysis_runs_to_completion_and_emits_done():
    registry = RunRegistry()
    fake = _FakeGraph([{"market_report": "a"}, {"final_trade_decision": "BUY"}])
    req = AnalysisRequest(ticker="TEST", trade_date="2026-01-01")

    handle = await start_analysis(req, registry, graph_factory=lambda cfg: fake)

    events = []
    while True:
        evt = await asyncio.wait_for(handle.queue.get(), timeout=2.0)
        events.append(evt)
        if evt["type"] == "done":
            break

    assert handle.status == RunStatus.DONE
    assert handle.final_state == {"market_report": "a", "final_trade_decision": "BUY"}
    chunk_events = [e for e in events if e["type"] == "chunk"]
    assert len(chunk_events) == 2
    assert chunk_events[0]["payload"] == {"market_report": "a"}


@pytest.mark.asyncio
async def test_abort_sets_cancel_event_and_transitions_to_aborted():
    registry = RunRegistry()
    fake = _FakeGraph([{"market_report": f"chunk-{i}"} for i in range(20)])
    req = AnalysisRequest(ticker="TEST", trade_date="2026-01-01")

    handle = await start_analysis(req, registry, graph_factory=lambda cfg: fake)
    handle.cancel_event.set()
    await asyncio.wait_for(handle.task, timeout=2.0)
    assert handle.status == RunStatus.ABORTED


@pytest.mark.asyncio
async def test_graph_exception_marks_run_as_error():
    registry = RunRegistry()

    class _BoomGraph:
        def propagate(self, *args, **kwargs):
            raise ValueError("kaboom")

    req = AnalysisRequest(ticker="TEST", trade_date="2026-01-01")
    handle = await start_analysis(req, registry, graph_factory=lambda cfg: _BoomGraph())
    await asyncio.wait_for(handle.task, timeout=2.0)
    assert handle.status == RunStatus.ERROR
    assert handle.error and "kaboom" in handle.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_runner.py -v`
Expected: FAIL — `backend.services.runner` doesn't exist.

- [ ] **Step 3: Implement the runner**

Create `backend/services/runner.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.services.registry import RunHandle, RunRegistry

logger = logging.getLogger(__name__)


@dataclass
class AnalysisRequest:
    ticker: str
    trade_date: str
    config_overrides: dict[str, Any] = field(default_factory=dict)


def _default_graph_factory(cfg: dict[str, Any]):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    merged = {**DEFAULT_CONFIG, **cfg}
    return TradingAgentsGraph(config=merged)


async def start_analysis(
    request: AnalysisRequest,
    registry: RunRegistry,
    graph_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> RunHandle:
    # Resolve at call time (NOT in the default value) so monkeypatching
    # `_default_graph_factory` from tests works as expected.
    factory = graph_factory if graph_factory is not None else _default_graph_factory
    handle = registry.register()
    handle.task = asyncio.create_task(
        _run(handle, request, factory),
        name=f"analysis-{handle.run_id}",
    )
    return handle


async def _run(
    handle: RunHandle,
    request: AnalysisRequest,
    graph_factory: Callable[[dict[str, Any]], Any],
) -> None:
    loop = asyncio.get_running_loop()
    await handle.mark_running()

    def _emit_chunk(chunk: dict[str, Any]) -> None:
        # Bridge sync engine callback to the asyncio queue.
        coro = handle.emit({"type": "chunk", "payload": chunk})
        asyncio.run_coroutine_threadsafe(coro, loop)

    def _sync_runner() -> dict[str, Any]:
        graph = graph_factory(request.config_overrides)
        return graph.propagate(
            request.ticker,
            request.trade_date,
            on_chunk=_emit_chunk,
            cancel_event=handle.cancel_event,
        )

    try:
        final_state = await asyncio.to_thread(_sync_runner)
    except RuntimeError as exc:
        if "cancelled" in str(exc).lower():
            await handle.mark_aborted()
            return
        logger.exception("Analysis %s failed", handle.run_id)
        await handle.mark_error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - surface every engine failure
        logger.exception("Analysis %s failed", handle.run_id)
        await handle.mark_error(str(exc))
        return

    await handle.mark_done(final_state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_runner.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add backend/services/runner.py tests/backend/test_runner.py
git commit -m "feat(backend): add async runner bridging engine to asyncio queue"
```

---

## Task 5: Analysis routes (POST /start, WS /ws/{id}, POST /{id}/abort)

**Files:**
- Create: `backend/schemas.py`, `backend/routes/analysis.py`
- Modify: `backend/main.py` (register router + registry singleton)
- Create: `tests/backend/test_analysis_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/backend/test_analysis_routes.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.registry import RunRegistry


class _FakeGraph:
    def __init__(self, chunks):
        self._chunks = chunks

    def propagate(self, company_name, trade_date, on_chunk=None, cancel_event=None):
        for chunk in self._chunks:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Analysis cancelled by caller")
            if on_chunk is not None:
                on_chunk(chunk)
        final = {}
        for c in self._chunks:
            final.update(c)
        return final


@pytest.fixture
def app_with_fake_graph(monkeypatch):
    from backend.services import runner as runner_module

    fake_chunks = [{"market_report": "draft"}, {"final_trade_decision": "BUY"}]
    monkeypatch.setattr(
        runner_module, "_default_graph_factory", lambda cfg: _FakeGraph(fake_chunks)
    )
    app = create_app()
    app.state.registry = RunRegistry()  # fresh registry per test
    return app


def test_start_returns_run_id(app_with_fake_graph):
    client = TestClient(app_with_fake_graph)
    resp = client.post(
        "/api/analysis/start",
        json={"ticker": "TEST", "trade_date": "2026-01-01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert len(data["run_id"]) >= 8


def test_websocket_streams_events_until_done(app_with_fake_graph):
    client = TestClient(app_with_fake_graph)
    resp = client.post(
        "/api/analysis/start",
        json={"ticker": "TEST", "trade_date": "2026-01-01"},
    )
    run_id = resp.json()["run_id"]

    received = []
    with client.websocket_connect(f"/api/analysis/ws/{run_id}") as ws:
        while True:
            msg = json.loads(ws.receive_text())
            received.append(msg)
            if msg["type"] == "done":
                break

    types = [m["type"] for m in received]
    assert "status" in types or "chunk" in types
    assert types[-1] == "done"


def test_websocket_unknown_run_id_closes_with_4404(app_with_fake_graph):
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app_with_fake_graph)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/analysis/ws/nonexistent") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4404


def test_abort_transitions_run_to_aborted(monkeypatch):
    from backend.services import runner as runner_module

    long_chunks = [{"market_report": f"c-{i}"} for i in range(200)]
    monkeypatch.setattr(
        runner_module, "_default_graph_factory", lambda cfg: _FakeGraph(long_chunks)
    )
    app = create_app()
    app.state.registry = RunRegistry()
    client = TestClient(app)

    start = client.post(
        "/api/analysis/start",
        json={"ticker": "TEST", "trade_date": "2026-01-01"},
    )
    run_id = start.json()["run_id"]

    abort = client.post(f"/api/analysis/{run_id}/abort")
    assert abort.status_code == 200

    with client.websocket_connect(f"/api/analysis/ws/{run_id}") as ws:
        for _ in range(500):
            msg = json.loads(ws.receive_text())
            if msg["type"] in {"aborted", "done"}:
                assert msg["type"] == "aborted"
                break
        else:
            pytest.fail("Did not reach aborted state")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_analysis_routes.py -v`
Expected: FAIL — `/api/analysis/*` routes don't exist.

- [ ] **Step 3: Add schemas**

Create `backend/schemas.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    trade_date: str = Field(..., description="YYYY-MM-DD")
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class StartAnalysisResponse(BaseModel):
    run_id: str


class AbortResponse(BaseModel):
    run_id: str
    status: str
```

- [ ] **Step 4: Wire registry into main**

Update `backend/main.py` to attach the registry on `app.state` and include the analysis router:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.deps import settings_singleton
from backend.routes import analysis, health
from backend.services.registry import RunRegistry


def create_app() -> FastAPI:
    settings = settings_singleton()
    app = FastAPI(title="TradingAgents Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = RunRegistry()
    app.include_router(health.router)
    app.include_router(analysis.router)
    return app


app = create_app()
```

- [ ] **Step 5: Implement analysis routes**

Create `backend/routes/analysis.py`:

```python
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from backend.deps import get_registry
from backend.schemas import AbortResponse, StartAnalysisRequest, StartAnalysisResponse
from backend.services.registry import RunRegistry
from backend.services.runner import AnalysisRequest, start_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/start", response_model=StartAnalysisResponse)
async def start(
    body: StartAnalysisRequest,
    registry: RunRegistry = Depends(get_registry),
) -> StartAnalysisResponse:
    handle = await start_analysis(
        AnalysisRequest(
            ticker=body.ticker,
            trade_date=body.trade_date,
            config_overrides=body.config_overrides,
        ),
        registry,
    )
    return StartAnalysisResponse(run_id=handle.run_id)


@router.post("/{run_id}/abort", response_model=AbortResponse)
async def abort(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> AbortResponse:
    handle = registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    handle.cancel_event.set()
    return AbortResponse(run_id=run_id, status=handle.status.value)


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

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/backend/test_analysis_routes.py -v`
Expected: PASS (all four).

- [ ] **Step 7: Commit**

```bash
git add backend/schemas.py backend/routes/analysis.py backend/main.py tests/backend/test_analysis_routes.py
git commit -m "feat(backend): add analysis start/ws/abort routes"
```

---

## Task 6: History service + routes (GET /history, PATCH /history/{ticker}/{date})

We expose `tradingagents.storage.sqlite_history` as JSON. Add a `user_rating` column + `set_rating` helper if missing.

**Files:**
- Maybe modify: `tradingagents/storage/sqlite_history.py` (add `user_rating` column + `set_rating`)
- Create: `backend/services/history.py`, `backend/routes/history.py`
- Modify: `backend/main.py` (register history router)
- Create: `tests/backend/test_history_routes.py`

- [ ] **Step 1: Inspect sqlite_history schema**

Run: `grep -nE "rating|set_note|user_rating|notes TEXT|CREATE TABLE" /Users/tonniclaw/TradingAgents-WebUI/tradingagents/storage/sqlite_history.py`

Read the file around `_init_schema` (line 64) and `set_note` (line 262). If a `user_rating` column or `set_rating` helper is missing, you will add them in Step 4.

- [ ] **Step 2: Write failing history route tests**

Create `tests/backend/test_history_routes.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seeded_results(tmp_path: Path, monkeypatch):
    ticker_dir = tmp_path / "TEST" / "2026-01-01"
    (ticker_dir / "reports").mkdir(parents=True)
    (ticker_dir / "final_state.json").write_text(
        json.dumps({"final_trade_decision": "BUY: strong signal", "market_report": "x"})
    )
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))

    from tradingagents.storage import sqlite_history

    sqlite_history.rebuild_from_disk(tmp_path)
    return tmp_path


def _client():
    from backend.main import create_app

    return TestClient(create_app())


def test_history_list_returns_seeded_record(seeded_results):
    resp = _client().get("/api/history")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["ticker"] == "TEST" for item in items)


def test_history_filter_by_ticker(seeded_results):
    resp = _client().get("/api/history?ticker=TEST")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and all(item["ticker"] == "TEST" for item in items)


def test_patch_history_sets_note(seeded_results):
    from tradingagents.storage import sqlite_history

    resp = _client().patch(
        "/api/history/TEST/2026-01-01",
        json={"note": "Reviewed — good thesis"},
    )
    assert resp.status_code == 200
    note = sqlite_history.get_note(seeded_results, "TEST", "2026-01-01")
    assert note == "Reviewed — good thesis"


def test_patch_history_sets_rating(seeded_results):
    resp = _client().patch(
        "/api/history/TEST/2026-01-01",
        json={"rating": "good"},
    )
    assert resp.status_code in {200, 501}  # 501 if rating not yet implemented
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/backend/test_history_routes.py -v`
Expected: FAIL — `/api/history` doesn't exist.

- [ ] **Step 4: Add `user_rating` column + `set_rating` helper IF MISSING**

If Step 1 showed no `user_rating` column, modify `tradingagents/storage/sqlite_history.py`:

a. In `_init_schema`, after the existing column definitions, add (match the file's existing migration idiom — typically a `try/except sqlite3.OperationalError`):

```python
    try:
        conn.execute("ALTER TABLE analyses ADD COLUMN user_rating TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
```

b. Near `set_note`, add:

```python
def set_rating(results_dir: Path | str, ticker: str, trade_date: str, rating: str) -> None:
    conn = _connect(Path(results_dir))
    try:
        conn.execute(
            "UPDATE analyses SET user_rating = ? WHERE ticker = ? AND trade_date = ?",
            (rating, ticker, trade_date),
        )
        conn.commit()
    finally:
        conn.close()
```

If the helper already exists, skip this step.

- [ ] **Step 5: Implement history service + router**

Create `backend/services/history.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from tradingagents.storage import sqlite_history


def list_analyses(
    results_dir: Path,
    ticker: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    return sqlite_history.query_analyses(results_dir, ticker=ticker, query=query)


def set_note(results_dir: Path, ticker: str, trade_date: str, note: str) -> None:
    sqlite_history.set_note(results_dir, ticker, trade_date, note)


def set_rating(results_dir: Path, ticker: str, trade_date: str, rating: str) -> None:
    if hasattr(sqlite_history, "set_rating"):
        sqlite_history.set_rating(results_dir, ticker, trade_date, rating)
    else:
        raise NotImplementedError("set_rating not yet supported by sqlite_history")
```

Create `backend/routes/history.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import settings_singleton
from backend.services import history as history_service

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryListResponse(BaseModel):
    items: list[dict]


class PatchHistoryRequest(BaseModel):
    note: str | None = None
    rating: str | None = None


@router.get("", response_model=HistoryListResponse)
def list_history(
    ticker: str | None = None,
    q: str | None = None,
) -> HistoryListResponse:
    settings = settings_singleton()
    items = history_service.list_analyses(settings.results_dir, ticker=ticker, query=q)
    return HistoryListResponse(items=items)


@router.patch("/{ticker}/{trade_date}")
def patch_history(ticker: str, trade_date: str, body: PatchHistoryRequest) -> dict:
    settings = settings_singleton()
    if body.note is not None:
        history_service.set_note(settings.results_dir, ticker, trade_date, body.note)
    if body.rating is not None:
        try:
            history_service.set_rating(settings.results_dir, ticker, trade_date, body.rating)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
    return {"ticker": ticker, "trade_date": trade_date, "updated": True}
```

Register the router in `backend/main.py`:

```python
from backend.routes import analysis, health, history
```

And in `create_app()`:

```python
    app.include_router(history.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/backend/test_history_routes.py -v`
Expected: PASS (all four — the rating test accepts either 200 or 501 depending on whether you added `set_rating`).

- [ ] **Step 7: Commit**

```bash
git add backend/services/history.py backend/routes/history.py backend/main.py tests/backend/test_history_routes.py tradingagents/storage/sqlite_history.py
git commit -m "feat(backend): add history list + patch (note/rating) endpoints"
```

---

## Task 7: Manual smoke test with the real engine

This is manual verification, not automated. It proves the streaming spine works against the real `TradingAgentsGraph` end-to-end.

**Files:** none

- [ ] **Step 1: Start the backend with the real engine**

Run: `uvicorn backend.main:app --port 8765 --reload`

- [ ] **Step 2: Kick off a small analysis from the shell**

In another terminal:

```bash
curl -s -X POST http://localhost:8765/api/analysis/start \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","trade_date":"2026-01-02","config_overrides":{"max_debate_rounds":1,"max_risk_discuss_rounds":1}}'
```

Expected: `{"run_id":"<hex>"}`. Note the run_id.

- [ ] **Step 3: Subscribe to the WebSocket**

Run (replace `<run_id>`):

```bash
python -c "
import asyncio, json, websockets
async def main():
    async with websockets.connect('ws://localhost:8765/api/analysis/ws/<run_id>') as ws:
        async for msg in ws:
            evt = json.loads(msg)
            keys = list(evt.get('payload', {}).keys()) if evt.get('payload') else ''
            print(evt['type'], keys)
            if evt['type'] in ('done','error','aborted'): break
asyncio.run(main())
"
```

Expected: Stream of `status`, `chunk`, `chunk`, ..., `done`. Each `chunk.payload` keys match the agent that just produced output (`market_report`, `sentiment_report`, ...). The run completes and final state appears in `results/AAPL/2026-01-02/`.

- [ ] **Step 4: Verify history endpoint sees the new run**

Run: `curl -s 'http://localhost:8765/api/history?ticker=AAPL' | python -m json.tool | head -20`
Expected: An item with `ticker: AAPL`, `trade_date: 2026-01-02`.

- [ ] **Step 5: Test abort mid-run**

Start a fresh analysis, capture run_id, then abort within ~5 seconds:

```bash
curl -X POST http://localhost:8765/api/analysis/<run_id>/abort
```

Reconnect WS — expect an `aborted` event.

- [ ] **Step 6: No commit needed (manual verification)**

If anything fails, fix in the relevant earlier task and re-run. Do NOT add band-aid error handling here.

---

## Task 8: Docs

**Files:**
- Create: `docs/backend.md`

- [ ] **Step 1: Write the backend doc**

Create `docs/backend.md`:

```markdown
# Backend (FastAPI)

The `backend/` package wraps the existing `tradingagents/` engine with a FastAPI HTTP/WebSocket layer. It runs alongside `webapp.py` (Streamlit) — both share the same engine, results directory, and SQLite index.

## Run

```bash
uvicorn backend.main:app --port 8765 --reload
```

Open http://localhost:8765/docs for the OpenAPI UI.

## Configuration

Environment variables (all prefixed `TRADINGAGENTS_`):

- `TRADINGAGENTS_RESULTS_DIR` — where analyses are stored. Defaults to `~/Desktop/Stock`.
- `TRADINGAGENTS_CORS_ORIGINS` — comma-separated origins allowed for the future React frontend. Defaults to `http://localhost:5173,http://127.0.0.1:5173`.

API keys are NOT managed by this layer in Step 1a. The engine still reads them from `.env` / `.ui_prefs.json` the same way `webapp.py` does today. A future `/api/providers/*` route (Step 1a.5) will manage keys explicitly.

## Endpoints (Step 1a)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| POST | `/api/analysis/start` | Body: `{ticker, trade_date, config_overrides}`. Returns `{run_id}`. |
| WS | `/api/analysis/ws/{run_id}` | Streams `{type: status/chunk/done/aborted/error/ping, ...}` |
| POST | `/api/analysis/{run_id}/abort` | Signals cancel — terminal event appears on the WS |
| GET | `/api/history?ticker=&q=` | List analyses |
| PATCH | `/api/history/{ticker}/{trade_date}` | Body: `{note?, rating?}` |

Endpoints deferred to Step 1a.5: providers, diagnostics, PDF download, history diff.

## Tests

```bash
pytest tests/backend -v
```

All backend tests use a fake graph and an isolated temp results dir — no LLM calls are made.

## Rollback

The state immediately before this work is tagged + branched as `pre-fastapi-refactor` (commit `b84edd6`). To revert completely:

\`\`\`bash
git reset --hard pre-fastapi-refactor
\`\`\`

Or to compare:

\`\`\`bash
git diff pre-fastapi-refactor..HEAD -- backend/ tradingagents/graph/trading_graph.py
\`\`\`
```

- [ ] **Step 2: Commit**

```bash
git add docs/backend.md
git commit -m "docs(backend): add run + rollback instructions"
```

---

## Task 9: Final verification + Step 1a close-out

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests + all `tests/backend/*` tests pass.

- [ ] **Step 2: Verify the rollback tag is still intact**

Run: `git tag -l pre-fastapi-refactor && git branch --list pre-fastapi-refactor`
Expected: Both exist and point at `b84edd6`.

- [ ] **Step 3: Verify Streamlit still launches**

Run: `streamlit run webapp.py --server.headless true` in the background; reach `http://localhost:8501`; stop.
Expected: No new errors related to engine changes.

- [ ] **Step 4: Tag the Step 1a completion point**

```bash
git tag -a step-1a-backend-complete -m "FastAPI backend Step 1a complete; Streamlit untouched"
```

- [ ] **Step 5: Update this plan**

Check off completed steps if useful — the tag is the source of truth either way.

---

## What's not in this plan (deferred)

- **Step 1a.5:** `/api/providers/*` (read/test/write keys with redaction), `/api/diagnostics/*`, `/api/runs/{id}/pdf`, `/api/history/{id}/diff/{otherId}`. PDF generation will be moved from `webapp.py` into `backend/services/pdf.py` at that time.
- **Step 1b:** Rewire `webapp.py` to call the backend instead of importing `tradingagents/`. Step 1b is a separate plan because it touches all 2202 lines of Streamlit code.
- **Step 2:** React + Vite frontend, deleting Streamlit.
