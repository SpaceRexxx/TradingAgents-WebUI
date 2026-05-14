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
