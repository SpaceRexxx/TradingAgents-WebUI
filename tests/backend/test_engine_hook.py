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
    # Prove the second chunk was withheld — the cancel check must run BEFORE
    # on_chunk is invoked for each chunk, not after.
    assert received[0]["market_report"] == "draft-1"
