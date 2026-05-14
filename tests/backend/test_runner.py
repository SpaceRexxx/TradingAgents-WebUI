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
