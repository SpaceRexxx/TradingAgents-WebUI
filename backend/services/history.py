from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tradingagents.storage import sqlite_history

logger = logging.getLogger(__name__)


def list_analyses(
    results_dir: Path,
    ticker: str | None = None,
) -> list[dict[str, Any]]:
    return sqlite_history.query_analyses(results_dir, ticker=ticker)


def reindex(results_dir: Path | str) -> dict[str, int]:
    """Recover analyses that exist on disk but aren't in the history index.

    Two-stage:
    1. For every `*/TradingAgentsStrategy_logs/full_states_log_*.json` whose
       `<ticker>/<trade_date>/final_state_report.json` is missing (the engine
       wrote its own log but backend persistence failed — e.g. the old
       propagate-tuple bug), materialize the report from the log so it is
       indexable and usable by the PDF/diff endpoints.
    2. Run sqlite_history.rebuild_from_disk to index every report not yet
       in the DB.

    Idempotent. Returns {"recovered": <reports written>, "indexed": <new rows>}.
    """
    results_dir = Path(results_dir)
    recovered = 0
    if results_dir.exists():
        for log_path in results_dir.rglob("full_states_log_*.json"):
            try:
                if log_path.parent.name != "TradingAgentsStrategy_logs":
                    continue
                ticker = log_path.parent.parent.name
                with open(log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                trade_date = str(data.get("trade_date") or "").strip()
                if not trade_date:
                    continue
                target = results_dir / ticker / trade_date / "final_state_report.json"
                if target.exists():
                    continue
                report = {k: v for k, v in data.items() if k != "messages"}
                # final_state schema uses trader_investment_plan; the engine
                # log stores it as trader_investment_decision.
                report.setdefault(
                    "trader_investment_plan",
                    data.get("trader_investment_decision", ""),
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=4)
                recovered += 1
            except Exception:
                logger.exception("Reindex: failed to recover %s", log_path)
                continue

    indexed = sqlite_history.rebuild_from_disk(results_dir)
    return {"recovered": recovered, "indexed": indexed}


def set_note(results_dir: Path, ticker: str, trade_date: str, note: str) -> None:
    sqlite_history.set_note(results_dir, ticker, trade_date, note)


def set_rating(results_dir: Path, ticker: str, trade_date: str, rating: str) -> bool:
    return sqlite_history.set_rating(results_dir, ticker, trade_date, rating)
