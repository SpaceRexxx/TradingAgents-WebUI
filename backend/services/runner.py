from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.services.persistence import persist_run
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
    import concurrent.futures

    loop = asyncio.get_running_loop()
    await handle.mark_running()

    # Track in-flight chunk futures so we can drain them before marking done.
    _chunk_futures: list[concurrent.futures.Future] = []

    def _emit_chunk(chunk: dict[str, Any]) -> None:
        # Bridge sync engine callback to the asyncio queue.
        coro = handle.emit({"type": "chunk", "payload": chunk})
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        _chunk_futures.append(fut)

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
