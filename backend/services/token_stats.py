from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from hashlib import sha1

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

CUMULATIVE_FILENAME = "cumulative_stats.json"

# DeepSeek V4 estimated pricing (USD / 1M tokens). Ported verbatim from the
# now-removed Streamlit UI's pricing table. Actual prices per provider.
_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.50, 1.50),
    "deepseek-v4-pro": (1.00, 3.00),
    "gpt-4o": (5.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
}

_ZERO_CUMULATIVE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "cost_usd": 0.0,
    "tool_calls": 0,
    "runs": 0,
}


class TokenAccumulator:
    """Accumulates token usage + tool-call counts from streamed LangGraph
    chunks. LangGraph chunks can repeat the cumulative message list, so each
    model response is summed once using a stable message/usage fingerprint.
    """

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.cached_input_tokens = 0
        self.uncached_input_tokens = 0
        self.tool_calls: dict[str, int] = {}
        self._seen_usage: set[str] = set()
        self._seen_tool_calls: set[str] = set()

    def feed(self, chunk: dict[str, Any]) -> None:
        msgs = chunk.get("messages") or []
        if not msgs:
            return
        for msg in msgs[-3:]:
            self.feed_message(msg)

    def feed_message(self, msg: Any) -> None:
        usage = self._extract_usage(msg)
        if isinstance(usage, dict):
            it = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            ot = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            tt = usage.get("total_tokens") or (it + ot)
            cached = self._cached_input_tokens(usage)
            uncached = self._uncached_input_tokens(usage)
            if tt:
                usage_key = self._message_key(msg, usage, "usage")
                if usage_key not in self._seen_usage:
                    self._seen_usage.add(usage_key)
                    self.input_tokens += int(it)
                    self.output_tokens += int(ot)
                    self.total_tokens += int(tt)
                    self.cached_input_tokens += cached
                    self.uncached_input_tokens += uncached
        tc = getattr(msg, "tool_calls", None)
        if tc:
            for index, call in enumerate(tc):
                name = (
                    call.get("name")
                    if isinstance(call, dict)
                    else getattr(call, "name", None)
                )
                call_id = (
                    call.get("id")
                    if isinstance(call, dict)
                    else getattr(call, "id", None)
                )
                tool_key = str(call_id) if call_id else self._message_key(msg, {"tool": name, "index": index}, "tool")
                if name and tool_key not in self._seen_tool_calls:
                    self._seen_tool_calls.add(tool_key)
                    self.tool_calls[name] = self.tool_calls.get(name, 0) + 1

    def feed_llm_result(self, response: Any, run_id: str | None = None) -> None:
        fed_message_usage = False
        for batch in getattr(response, "generations", []) or []:
            for generation in batch:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                before = len(self._seen_usage)
                self.feed_message(message)
                fed_message_usage = fed_message_usage or len(self._seen_usage) > before
        if fed_message_usage:
            return

        llm_output = getattr(response, "llm_output", None)
        if not isinstance(llm_output, dict):
            return
        usage = llm_output.get("token_usage") or llm_output.get("usage") or llm_output
        if not isinstance(usage, dict):
            return
        pseudo = _UsageMessage(
            usage_metadata=usage,
            content=llm_output.get("model_name", "") or "",
            id=f"llm-result:{run_id}" if run_id else None,
        )
        self.feed_message(pseudo)

    @staticmethod
    def _message_key(msg: Any, payload: dict[str, Any], kind: str) -> str:
        msg_id = getattr(msg, "id", None)
        if msg_id:
            return f"{kind}:{msg_id}"
        content = getattr(msg, "content", "")
        raw = json.dumps(
            {"kind": kind, "payload": payload, "content": content},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_usage(msg: Any) -> dict[str, Any]:
        usage = getattr(msg, "usage_metadata", None)
        if isinstance(usage, dict):
            return usage
        metadata = getattr(msg, "response_metadata", {})
        if not isinstance(metadata, dict):
            return {}
        token_usage = metadata.get("token_usage") or metadata.get("usage")
        if isinstance(token_usage, dict):
            return token_usage
        return metadata

    @staticmethod
    def _cached_input_tokens(usage: dict[str, Any]) -> int:
        details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
        candidates = [
            usage.get("prompt_cache_hit_tokens"),
            usage.get("cache_hit_tokens"),
            usage.get("cached_tokens"),
            details.get("cache_read") if isinstance(details, dict) else None,
            details.get("cached_tokens") if isinstance(details, dict) else None,
        ]
        return int(next((v for v in candidates if v), 0) or 0)

    @staticmethod
    def _uncached_input_tokens(usage: dict[str, Any]) -> int:
        details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
        candidates = [
            usage.get("prompt_cache_miss_tokens"),
            usage.get("cache_miss_tokens"),
            details.get("cache_miss") if isinstance(details, dict) else None,
        ]
        return int(next((v for v in candidates if v), 0) or 0)

    def result(self, model: str | None = None) -> dict[str, Any]:
        in_price, out_price = _PRICING.get(model or "", (0.0, 0.0))
        cost = (self.input_tokens * in_price + self.output_tokens * out_price) / 1_000_000
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens or (self.input_tokens + self.output_tokens),
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "cost_usd": round(cost, 4),
            "tool_calls": dict(self.tool_calls),
            "tool_call_count": sum(self.tool_calls.values()),
        }


class _UsageMessage:
    def __init__(self, usage_metadata: dict[str, Any], content: str = "", id: str | None = None):
        self.usage_metadata = usage_metadata
        self.response_metadata = {}
        self.tool_calls = []
        self.content = content
        self.id = id


class TokenUsageCallback(BaseCallbackHandler):
    """Collect token usage directly from every LangChain LLM run."""

    def __init__(self, accumulator: TokenAccumulator):
        super().__init__()
        self.accumulator = accumulator

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        self.accumulator.feed_llm_result(response, run_id=str(run_id))


def _cumulative_path(results_dir: Path | str) -> Path:
    return Path(results_dir) / CUMULATIVE_FILENAME


def load_cumulative(results_dir: Path | str) -> dict[str, Any]:
    """Read aggregate token/cost/tool stats across all analyses; zeros if
    missing or unreadable. Back-fills missing keys for old files."""
    p = _cumulative_path(results_dir)
    if not p.exists():
        return dict(_ZERO_CUMULATIVE)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, default in _ZERO_CUMULATIVE.items():
            data.setdefault(k, default)
        return data
    except Exception:
        return dict(_ZERO_CUMULATIVE)


def accumulate_cumulative(
    results_dir: Path | str,
    run_stats: dict[str, Any],
) -> dict[str, Any]:
    """Add one run's stats to cumulative_stats.json. Each backend run executes
    its success path exactly once, so no run_id dedup is needed (unlike the
    Streamlit rerun model). Returns the updated cumulative dict."""
    cum = load_cumulative(results_dir)
    cum["input_tokens"] += int(run_stats.get("input_tokens", 0) or 0)
    cum["output_tokens"] += int(run_stats.get("output_tokens", 0) or 0)
    cum["total_tokens"] += int(run_stats.get("total_tokens", 0) or 0)
    cum["cost_usd"] = round(float(cum["cost_usd"]) + float(run_stats.get("cost_usd", 0.0) or 0.0), 4)
    cum["tool_calls"] += int(run_stats.get("tool_call_count", 0) or 0)
    cum["runs"] += 1
    try:
        p = _cumulative_path(results_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cum, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to write %s", CUMULATIVE_FILENAME)
    return cum
