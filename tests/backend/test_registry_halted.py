import asyncio
import pytest

from backend.services.registry import RunHandle, RunStatus


@pytest.mark.asyncio
async def test_mark_halted_sets_status_and_emits_event():
    h = RunHandle(run_id="rid")
    await h.mark_halted(["market"])
    assert h.status == RunStatus.HALTED
    ev = await asyncio.wait_for(h.queue.get(), timeout=1.0)
    assert ev == {"type": "halted", "failed_analysts": ["market"]}


def test_retry_count_initially_zero_per_analyst():
    h = RunHandle(run_id="rid")
    assert h.retry_count_by_analyst == {}
    assert h.get_retry_count("market") == 0


def test_retry_count_increments():
    h = RunHandle(run_id="rid")
    h.increment_retry("market")
    h.increment_retry("market")
    h.increment_retry("news")
    assert h.get_retry_count("market") == 2
    assert h.get_retry_count("news") == 1
    assert h.get_retry_count("fundamentals") == 0


def test_retry_lock_acquire_release():
    h = RunHandle(run_id="rid")
    assert h.try_acquire_retry_lock() is True
    assert h.try_acquire_retry_lock() is False  # already held
    h.release_retry_lock()
    assert h.try_acquire_retry_lock() is True


def test_is_terminal_includes_halted():
    h = RunHandle(run_id="rid")
    h.status = RunStatus.HALTED
    assert h.is_terminal() is True


def test_mark_halted_copies_failed_list_not_aliases():
    """mark_halted should not store a reference to the caller's list."""
    h = RunHandle(run_id="rid")
    src = ["market"]
    import asyncio as _asyncio
    _asyncio.get_event_loop().run_until_complete(h.mark_halted(src))
    # mutate the source list after the call
    src.append("news")
    # event should already have been emitted with the original list copy
    ev = _asyncio.get_event_loop().run_until_complete(_asyncio.wait_for(h.queue.get(), timeout=1.0))
    assert ev["failed_analysts"] == ["market"]
