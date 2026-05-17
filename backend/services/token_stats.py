from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CUMULATIVE_FILENAME = "cumulative_stats.json"

# DeepSeek V4 estimated pricing (USD / 1M tokens). Ported verbatim from the
# now-removed Streamlit UI's pricing table. Actual prices per provider.
_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.50, 1.50),
    "deepseek-v4-pro": (1.00, 3.00),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
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
    chunks. Ported from the now-removed Streamlit UI — chunks are cumulative
    streams, so per-field we keep the running max rather than summing.
    """

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.tool_calls: dict[str, int] = {}

    def feed(self, chunk: dict[str, Any]) -> None:
        msgs = chunk.get("messages") or []
        if not msgs:
            return
        for msg in msgs[-3:]:
            usage = getattr(msg, "usage_metadata", None)
            if not isinstance(usage, dict):
                usage = getattr(msg, "response_metadata", {})
            if isinstance(usage, dict):
                it = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                ot = usage.get("output_tokens") or usage.get("completion_tokens") or 0
                tt = usage.get("total_tokens") or (it + ot)
                if tt:
                    self.input_tokens = max(self.input_tokens, int(it))
                    self.output_tokens = max(self.output_tokens, int(ot))
                    self.total_tokens = max(self.total_tokens, int(tt))
            tc = getattr(msg, "tool_calls", None)
            if tc:
                for call in tc:
                    name = (
                        call.get("name")
                        if isinstance(call, dict)
                        else getattr(call, "name", None)
                    )
                    if name:
                        self.tool_calls[name] = self.tool_calls.get(name, 0) + 1

    def result(self, model: str | None = None) -> dict[str, Any]:
        in_price, out_price = _PRICING.get(model or "", (0.0, 0.0))
        cost = (self.input_tokens * in_price + self.output_tokens * out_price) / 1_000_000
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens or (self.input_tokens + self.output_tokens),
            "cost_usd": round(cost, 4),
            "tool_calls": dict(self.tool_calls),
            "tool_call_count": sum(self.tool_calls.values()),
        }


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
