from __future__ import annotations

from pathlib import Path
from typing import Any

from tradingagents.storage import sqlite_history


def list_analyses(
    results_dir: Path,
    ticker: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    # query_analyses does not support full-text search yet; query param ignored
    return sqlite_history.query_analyses(results_dir, ticker=ticker)


def set_note(results_dir: Path, ticker: str, trade_date: str, note: str) -> None:
    sqlite_history.set_note(results_dir, ticker, trade_date, note)


def set_rating(results_dir: Path, ticker: str, trade_date: str, rating: str) -> None:
    if hasattr(sqlite_history, "set_rating"):
        sqlite_history.set_rating(results_dir, ticker, trade_date, rating)
    else:
        raise NotImplementedError("set_rating not yet supported by sqlite_history")
