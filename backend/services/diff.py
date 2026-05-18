from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from tradingagents.storage import sqlite_history

_DIFF_SECTIONS = [
    ("market_report", "市场分析报告"),
    ("sentiment_report", "舆情分析报告"),
    ("news_report", "新闻分析报告"),
    ("fundamentals_report", "基本面分析报告"),
    ("investment_debate_state.bull_history", "多头研究员辩论"),
    ("investment_debate_state.bear_history", "空头研究员辩论"),
    ("investment_plan", "研究经理总结"),
    ("trader_investment_plan", "交易员计划"),
    ("risk_debate_state.aggressive_history", "激进型分析师辩论"),
    ("risk_debate_state.conservative_history", "保守型分析师辩论"),
    ("risk_debate_state.neutral_history", "中立型分析师辩论"),
    ("final_trade_decision", "最终投资决策"),
]


class AnalysisNotFound(Exception):
    pass


def _load_final_state(results_dir, ticker: str, trade_date: str) -> dict:
    rows = sqlite_history.query_analyses(results_dir, ticker=ticker)
    match = next((r for r in rows if r["trade_date"] == trade_date), None)
    if match is None:
        raise AnalysisNotFound(f"{ticker} {trade_date}")
    p = Path(match["json_path"])
    if not p.exists():
        raise AnalysisNotFound(f"{ticker} {trade_date} (json missing)")
    return json.loads(p.read_text(encoding="utf-8"))


def _get_section(data: dict[str, Any], path: str) -> str:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part)
    return value.strip() if isinstance(value, str) else ""


def diff_analyses(
    results_dir,
    ticker_a: str,
    date_a: str,
    ticker_b: str,
    date_b: str,
) -> dict:
    a = _load_final_state(results_dir, ticker_a, date_a)
    b = _load_final_state(results_dir, ticker_b, date_b)

    sections: dict[str, dict] = {}
    for key, title in _DIFF_SECTIONS:
        va = _get_section(a, key)
        vb = _get_section(b, key)
        changed = va != vb
        diff_text = ""
        if changed:
            diff_text = "\n".join(
                difflib.unified_diff(
                    va.splitlines(),
                    vb.splitlines(),
                    fromfile=f"{ticker_a}@{date_a}:{key}",
                    tofile=f"{ticker_b}@{date_b}:{key}",
                    lineterm="",
                )
            )
        sections[key] = {
            "title": title,
            "changed": changed,
            "diff": diff_text,
            "a_text": va,
            "b_text": vb,
        }

    return {
        "a": {"ticker": ticker_a, "trade_date": date_a},
        "b": {"ticker": ticker_b, "trade_date": date_b},
        "sections": sections,
    }
