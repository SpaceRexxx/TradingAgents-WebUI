from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.deps import get_settings_dep
from backend.services import pdf as pdf_service
from tradingagents.storage import sqlite_history

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _load_indexed_final_state(ticker: str, trade_date: str) -> dict:
    settings = get_settings_dep()
    rows = sqlite_history.query_analyses(settings.results_dir, ticker=ticker)
    match = next((r for r in rows if r["trade_date"] == trade_date), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"No indexed analysis for {ticker} {trade_date}",
        )

    json_path = Path(match["json_path"])
    if not json_path.exists():
        # Generic message — do not leak the absolute on-disk path.
        raise HTTPException(
            status_code=404,
            detail=f"final_state file missing for {ticker} {trade_date}",
        )
    return json.loads(json_path.read_text(encoding="utf-8"))


@router.get("/{ticker}/{trade_date}/report")
async def get_run_report(ticker: str, trade_date: str) -> dict:
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "final_state": _load_indexed_final_state(ticker, trade_date),
    }


@router.get("/{ticker}/{trade_date}/pdf")
async def get_run_pdf(ticker: str, trade_date: str) -> Response:
    final_state = _load_indexed_final_state(ticker, trade_date)

    pdf_bytes = await asyncio.to_thread(
        pdf_service.generate_pdf, final_state, ticker, trade_date
    )
    # Sanitize path params before embedding in the Content-Disposition
    # header so a ticker like `A"x` cannot inject/break the header.
    safe_name = re.sub(r"[^\w.\-]", "_", f"{ticker}_{trade_date}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}.pdf"'},
    )
