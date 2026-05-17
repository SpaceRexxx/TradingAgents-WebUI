from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


AGENT_STREAM_KEYS = {
    "market": ("market_report", None, "market"),
    "social": ("sentiment_report", None, "social"),
    "news": ("news_report", None, "news"),
    "fundamentals": ("fundamentals_report", None, "fundamentals"),
    "bull": ("investment_debate_state", "bull_history", "bull"),
    "bear": ("investment_debate_state", "bear_history", "bear"),
    "research_manager": ("investment_debate_state", "judge_decision", "research_manager"),
    "trader": ("trader_investment_plan", None, "trader"),
    "aggressive": ("risk_debate_state", "aggressive_history", "aggressive"),
    "conservative": ("risk_debate_state", "conservative_history", "conservative"),
    "neutral": ("risk_debate_state", "neutral_history", "neutral"),
    "portfolio_manager": ("risk_debate_state", "judge_decision", "portfolio_manager"),
}

SENDER_TO_AGENT = {
    "Market Analyst": "market",
    "News Analyst": "news",
    "Fundamentals Analyst": "fundamentals",
    "Bull Researcher": "bull",
    "Bear Researcher": "bear",
    "Trader": "trader",
    "Risky Analyst": "aggressive",
    "Safe Analyst": "conservative",
    "Neutral Analyst": "neutral",
}


@dataclass
class _RunBuffer:
    agent_key: str
    text: str = ""
    last_emit: float = field(default_factory=lambda: 0.0)
    last_activity: float = field(default_factory=lambda: 0.0)


class LiveTokenCallback(BaseCallbackHandler):
    """Bridge LangChain content-token callbacks into existing WS chunks.

    Thinking/reasoning tokens are intentionally not surfaced here. Provider
    clients keep those in message metadata for API roundtrip; the UI receives
    only user-facing report content.
    """

    def __init__(self, emit_chunk, min_interval: float = 0.12, min_chars: int = 24):
        super().__init__()
        self._emit_chunk = emit_chunk
        self._min_interval = min_interval
        self._min_chars = min_chars
        self._runs: dict[str, _RunBuffer] = {}
        self._seen_agents: set[str] = set()
        self._lock = Lock()

    @property
    def seen_agents(self) -> set[str]:
        with self._lock:
            return set(self._seen_agents)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id,
        **kwargs,
    ) -> None:
        agent_key = _infer_agent_key(_messages_text(messages))
        if agent_key is None:
            return
        with self._lock:
            self._runs[str(run_id)] = _RunBuffer(agent_key=agent_key)
        self._emit_chunk(_activity_payload(agent_key, "started"))

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id,
        **kwargs,
    ) -> None:
        agent_key = _infer_agent_key("\n".join(prompts))
        if agent_key is None:
            return
        with self._lock:
            self._runs[str(run_id)] = _RunBuffer(agent_key=agent_key)
        self._emit_chunk(_activity_payload(agent_key, "started"))

    def on_llm_new_token(self, token: str, *, run_id, **kwargs) -> None:
        emit_payload: dict[str, Any] | None = None
        with self._lock:
            buf = self._runs.get(str(run_id))
            if buf is None:
                return
            now = time.monotonic()
            if not token:
                if not _has_reasoning_activity(kwargs):
                    return
                if now - buf.last_activity >= 1.0:
                    buf.last_activity = now
                    emit_payload = _activity_payload(buf.agent_key, "thinking")
                else:
                    return
            else:
                buf.text += token
                corrected = _infer_agent_key_from_output(buf.text)
                if corrected is not None and corrected != buf.agent_key:
                    buf.agent_key = corrected
                self._seen_agents.add(buf.agent_key)
                if (
                    token in {"\n", "\n\n"}
                    or len(buf.text) < self._min_chars
                    or now - buf.last_emit < self._min_interval
                ):
                    return
                buf.last_emit = now
                buf.last_activity = now
                emit_payload = _payload_for(buf.agent_key, buf.text, streaming=True)
        self._emit_chunk(emit_payload)

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        emit_payload: dict[str, Any] | None = None
        with self._lock:
            buf = self._runs.pop(str(run_id), None)
            if buf is None:
                return
            text = buf.text or _llm_result_text(response)
            if text:
                self._seen_agents.add(buf.agent_key)
                emit_payload = _payload_for(buf.agent_key, text, streaming=True)
        if emit_payload is not None:
            self._emit_chunk(emit_payload)

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        with self._lock:
            self._runs.pop(str(run_id), None)


def clear_streaming_payload(
    chunk: dict[str, Any],
    seen_agents: set[str] | None = None,
) -> dict[str, Any]:
    """Mark live previews complete when the graph emits the final node state."""
    if not seen_agents or "__streaming" in chunk:
        return chunk

    done: dict[str, bool] = {}
    sender = chunk.get("sender")
    if isinstance(sender, str) and sender in SENDER_TO_AGENT:
        agent_key = SENDER_TO_AGENT[sender]
        if agent_key in seen_agents:
            done[agent_key] = False

    for agent_key, (parent, child, _) in AGENT_STREAM_KEYS.items():
        if agent_key not in seen_agents:
            continue
        if child is None and chunk.get(parent):
            done[agent_key] = False
            continue
        value = chunk.get(parent)
        if child and isinstance(value, dict) and value.get(child):
            done[agent_key] = False

    if not done:
        return chunk
    return {**chunk, "__streaming": done}


def _payload_for(agent_key: str, text: str, streaming: bool) -> dict[str, Any]:
    parent, child, stream_key = AGENT_STREAM_KEYS[agent_key]
    display = _prefix(agent_key) + text
    payload: dict[str, Any]
    if child is None:
        payload = {parent: display}
    else:
        payload = {parent: {child: display}}
    payload["__streaming"] = {stream_key: streaming}
    return payload


def _activity_payload(agent_key: str, kind: str) -> dict[str, Any]:
    return {"__activity": {"agent": agent_key, "kind": kind}}


def _has_reasoning_activity(kwargs: dict[str, Any]) -> bool:
    chunk = kwargs.get("chunk")
    message = getattr(chunk, "message", None)
    additional = getattr(message, "additional_kwargs", None)
    return bool(isinstance(additional, dict) and additional.get("reasoning_content"))


def _prefix(agent_key: str) -> str:
    return {
        "bull": "Bull Analyst: ",
        "bear": "Bear Analyst: ",
        "aggressive": "激进型分析师: ",
        "conservative": "保守型分析师: ",
        "neutral": "中立型分析师: ",
    }.get(agent_key, "")


def _messages_text(messages: list[list[Any]]) -> str:
    parts: list[str] = []
    for batch in messages:
        for message in batch:
            content = getattr(message, "content", message)
            if isinstance(content, list):
                parts.extend(str(item) for item in content)
            else:
                parts.append(str(content))
    return "\n".join(parts)


def _infer_agent_key(text: str) -> str | None:
    checks = [
        # Match the active role instruction first. Later prompts embed earlier
        # reports, so broad data-source markers such as StockTwits/Xueqiu must
        # not win over the current agent's own system prompt.
        ("bull", ("你是一名多头分析师",)),
        ("bear", ("你是一名空头分析师",)),
        ("trader", ("你是一名分析市场数据以做出投资决策的交易代理",)),
        ("aggressive", ("作为激进型风险分析师", "激进型风险分析师", "高回报、高风险")),
        ("conservative", ("作为保守型风险分析师", "保守型风险分析师", "保护资产、最小化波动")),
        ("neutral", ("作为中立型风险分析师", "中立型风险分析师", "提供一个平衡的视角")),
        ("portfolio_manager", ("作为投资组合经理", "最终交易决策")),
        ("research_manager", ("作为高级研究经理", "投资委员会主席")),
        ("market", ("市场与技术面分析", "负责分析金融市场")),
        ("news", ("公司与宏观经济新闻分析", "新闻研究员")),
        ("fundamentals", ("基本面分析", "三大财务报表")),
        ("social", ("金融市场情绪分析师", "东方财富千股千评", "StockTwits", "雪球讨论流")),
    ]
    for agent_key, needles in checks:
        if any(needle in text for needle in needles):
            return agent_key
    return None


def _infer_agent_key_from_output(text: str) -> str | None:
    stripped = text.lstrip()
    checks = [
        ("aggressive", ("激进型分析师", "激进型风险分析师", "Risky Analyst")),
        ("conservative", ("保守型分析师", "保守型风险分析师", "Safe Analyst")),
        ("neutral", ("中立型分析师", "中立型风险分析师", "Neutral Analyst")),
        ("bull", ("Bull Analyst", "多头分析师")),
        ("bear", ("Bear Analyst", "空头分析师")),
        ("trader", ("交易员", "Trader")),
        ("research_manager", ("研究经理", "Research Manager")),
        ("portfolio_manager", ("投资组合经理", "Portfolio Manager")),
    ]
    for agent_key, prefixes in checks:
        if any(stripped.startswith(prefix) for prefix in prefixes):
            return agent_key
    return None


def _llm_result_text(response) -> str:
    try:
        generations = response.generations
    except Exception:
        return ""
    for batch in generations:
        for generation in batch:
            message = getattr(generation, "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str) and content:
                return content
            text = getattr(generation, "text", "")
            if isinstance(text, str) and text:
                return text
    return ""
