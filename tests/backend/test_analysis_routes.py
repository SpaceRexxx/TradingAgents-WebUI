import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.registry import RunRegistry


class _FakeGraph:
    """In-test stand-in for TradingAgentsGraph.

    `per_chunk_delay` lets the abort test deterministically widen the
    cancellation window: with 200 chunks at 1ms each the engine thread
    is guaranteed to still be running when the abort POST fires.
    """

    def __init__(self, chunks, per_chunk_delay: float = 0.0):
        self._chunks = chunks
        self._per_chunk_delay = per_chunk_delay

    def propagate(self, company_name, trade_date, on_chunk=None, cancel_event=None):
        for chunk in self._chunks:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Analysis cancelled by caller")
            if on_chunk is not None:
                on_chunk(chunk)
            if self._per_chunk_delay:
                time.sleep(self._per_chunk_delay)
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
    with TestClient(app_with_fake_graph) as client:
        resp = client.post(
            "/api/analysis/start",
            json={"ticker": "TEST", "trade_date": "2026-01-01"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert len(data["run_id"]) >= 8


def test_websocket_streams_events_until_done(app_with_fake_graph):
    # TestClient must be used as a context manager so the ASGI lifespan
    # portal stays alive across requests — otherwise the background
    # asyncio.Task created inside POST /start is torn down before the
    # WebSocket reader can drain the queue.
    with TestClient(app_with_fake_graph) as client:
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

    with TestClient(app_with_fake_graph) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/analysis/ws/nonexistent") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4404


def test_abort_transitions_run_to_aborted(monkeypatch):
    from backend.services import runner as runner_module

    long_chunks = [{"market_report": f"c-{i}"} for i in range(200)]
    monkeypatch.setattr(
        runner_module,
        "_default_graph_factory",
        lambda cfg: _FakeGraph(long_chunks, per_chunk_delay=0.001),
    )
    app = create_app()
    app.state.registry = RunRegistry()

    with TestClient(app) as client:
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
