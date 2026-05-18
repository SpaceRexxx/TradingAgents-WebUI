from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.services import pdf as pdf_service
from tradingagents.storage import sqlite_history

logger = logging.getLogger(__name__)


def persist_run(
    results_dir: Path | str,
    ticker: str,
    trade_date: str,
    final_state: dict[str, Any],
    model: str | None = None,
    provider: str | None = None,
    token_stats: dict[str, Any] | None = None,
) -> Path:
    """Write final_state_report.json/report.pdf and index it in sqlite_history."""
    results_dir = Path(results_dir)
    save_path = results_dir / ticker / trade_date
    save_path.mkdir(parents=True, exist_ok=True)

    serializable = {k: v for k, v in final_state.items() if k != "messages"}
    if token_stats is not None:
        serializable["token_stats"] = token_stats
    json_path = save_path / "final_state_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=4)

    pdf_path = save_path / "report.pdf"
    indexed_pdf_path: Path | None = None
    try:
        pdf_bytes = pdf_service.generate_pdf(serializable, ticker, trade_date)
        pdf_path.write_bytes(pdf_bytes)
        indexed_pdf_path = pdf_path
    except Exception:
        logger.exception("Failed to generate PDF report %s/%s", ticker, trade_date)

    try:
        sqlite_history.index_one_analysis(
            results_dir,
            ticker=ticker,
            trade_date=trade_date,
            json_path=str(json_path),
            pdf_path=indexed_pdf_path,
            decision_text=final_state.get("final_trade_decision", ""),
            model=model,
            provider=provider,
            has_position=None,
        )
    except Exception:
        logger.exception("Failed to index analysis %s/%s", ticker, trade_date)

    return json_path
