from __future__ import annotations

import difflib
import json
from pathlib import Path

from tradingagents.storage import sqlite_history

_DIFF_KEYS = [
    "market_report",
    "news_report",
    "sentiment_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
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
    for key in _DIFF_KEYS:
        va = (a.get(key) or "").strip()
        vb = (b.get(key) or "").strip()
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
        sections[key] = {"changed": changed, "diff": diff_text}

    return {
        "a": {"ticker": ticker_a, "trade_date": date_a},
        "b": {"ticker": ticker_b, "trade_date": date_b},
        "sections": sections,
    }
