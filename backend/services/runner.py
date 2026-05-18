from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.deps import get_settings_dep
from backend.services.live_tokens import CompositeCallback, LiveTokenCallback, clear_streaming_payload
from backend.services.persistence import persist_run
from backend.services.registry import RunHandle, RunRegistry
from backend.services.token_stats import TokenAccumulator, TokenUsageCallback, accumulate_cumulative

logger = logging.getLogger(__name__)


@dataclass
class AnalysisRequest:
    ticker: str
    trade_date: str
    config_overrides: dict[str, Any] = field(default_factory=dict)


def _default_graph_factory(cfg: dict[str, Any]):
    from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    # DEFAULT_CONFIG is frozen at import time; re-apply TRADINGAGENTS_* env
    # overrides on a copy so model/provider changes saved via /api/settings
    # take effect for new runs without a backend restart.
    base = _apply_env_overrides(dict(DEFAULT_CONFIG))
    merged = {**base, **cfg}
    callbacks = merged.pop("__callbacks", None)
    # `selected_analysts` is a TradingAgentsGraph constructor arg, not a config
    # key — pull it out of the merged config so the UI can choose analysts.
    selected = merged.pop("selected_analysts", None)
    if selected:
        return TradingAgentsGraph(selected, config=merged, callbacks=callbacks)
    return TradingAgentsGraph(config=merged, callbacks=callbacks)


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
    token_acc = TokenAccumulator()
    token_callback = TokenUsageCallback(token_acc)
    live_callback = LiveTokenCallback(lambda chunk: _emit_chunk(chunk))
    graph_callback = CompositeCallback(live_callback, token_callback)

    def _emit_chunk(chunk: dict[str, Any]) -> None:
        # Accumulate token/tool stats here while `chunk` still holds the raw
        # LangChain message objects (usage_metadata is lost after JSON WS
        # serialization downstream).
        token_acc.feed(chunk)
        chunk = clear_streaming_payload(chunk, live_callback.seen_agents)
        # Bridge sync engine callback to the asyncio queue.
        coro = handle.emit({"type": "chunk", "payload": chunk})
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        _chunk_futures.append(fut)

    engine_meta: dict[str, Any] = {}

    def _sync_runner() -> dict[str, Any]:
        # Force the engine to write where the backend reads (history/pdf
        # endpoints use Settings.results_dir). Without this the engine's
        # own results_dir can diverge and persisted runs become invisible.
        settings_results_dir = str(get_settings_dep().results_dir)
        factory_cfg = {
            **request.config_overrides,
            "results_dir": settings_results_dir,
            "__callbacks": [graph_callback],
        }
        graph = graph_factory(factory_cfg)
        cfg = getattr(graph, "config", {}) or {}
        engine_meta["results_dir"] = cfg.get("results_dir")
        engine_meta["model"] = cfg.get("deep_think_llm")
        engine_meta["provider"] = cfg.get("llm_provider")
        result = graph.propagate(
            request.ticker,
            request.trade_date,
            on_chunk=_emit_chunk,
            cancel_event=handle.cancel_event,
        )
        # The real engine returns (final_state, processed_signal); test fakes
        # return the state dict directly. Normalize to the state dict so
        # downstream persist/index/token logic always gets a mapping.
        if isinstance(result, tuple):
            result = result[0]
        return result

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

    token_stats = token_acc.result(engine_meta.get("model"))

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
                token_stats,
            )
        except Exception:
            logger.exception("Persist failed for %s", handle.run_id)
        try:
            await asyncio.to_thread(accumulate_cumulative, results_dir, token_stats)
        except Exception:
            logger.exception("Cumulative stats update failed for %s", handle.run_id)

    await handle.mark_done(final_state, token_stats)
