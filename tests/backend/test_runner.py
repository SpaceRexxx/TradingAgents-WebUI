import asyncio
from pathlib import Path

import pytest

from backend.services.registry import RunRegistry, RunStatus
from backend.services.runner import AnalysisRequest, start_analysis
from tradingagents.storage import sqlite_history


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


@pytest.mark.asyncio
async def test_abort_drains_chunks_before_aborted_event():
    """On abort, every chunk emitted before cancellation must appear in the
    queue BEFORE the 'aborted' terminal event.

    NOTE: this test passes with OR without the _drain() fix because the fake
    graph is fully synchronous — all run_coroutine_threadsafe puts are
    serviced by the loop before `await asyncio.to_thread(...)` returns, so no
    real ordering gap exists in-process. The race only manifests with a
    genuine async engine that yields between chunks. The test documents the
    intended ordering invariant and guards against a regression that removes
    the _drain() calls AND breaks queue ordering by other means.
    """
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


@pytest.mark.asyncio
async def test_engine_writes_to_settings_results_dir(tmp_path, monkeypatch):
    """The engine's results_dir must equal Settings.results_dir.

    Proves write-dir == backend-read-dir: persisted JSON + sqlite index must
    land in the same tmp dir that Settings reads. Fails before the fix
    (engine_meta.results_dir is None when factory ignores cfg; or the engine
    default diverges from Settings); passes after the fix forces results_dir
    to Settings.results_dir in _sync_runner.
    """
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))

    class _ConfigEchoGraph:
        def __init__(self, cfg):
            self.config = dict(cfg)

        def propagate(self, ticker, trade_date, on_chunk=None, cancel_event=None):
            if on_chunk:
                on_chunk({"market_report": "m"})
            return {
                "company_of_interest": ticker,
                "trade_date": trade_date,
                "final_trade_decision": "BUY",
            }

    registry = RunRegistry()
    handle = await start_analysis(
        AnalysisRequest(ticker="ZZZ", trade_date="2026-03-03"),
        registry,
        graph_factory=lambda cfg: _ConfigEchoGraph(cfg),
    )

    # Drain queue until done.
    while True:
        evt = await asyncio.wait_for(handle.queue.get(), timeout=5.0)
        if evt["type"] == "done":
            break

    # The persisted JSON must exist under the Settings dir (tmp_path).
    report_path = tmp_path / "ZZZ" / "2026-03-03" / "final_state_report.json"
    assert report_path.exists(), (
        f"final_state_report.json not found at {report_path}; "
        "engine wrote to a different results_dir than Settings.results_dir"
    )

    # The sqlite index must be queryable from the same dir.
    rows = sqlite_history.query_analyses(tmp_path, ticker="ZZZ")
    assert rows, (
        "sqlite index has no row for ZZZ in tmp_path; "
        "persist_run indexed a different directory than Settings.results_dir"
    )
