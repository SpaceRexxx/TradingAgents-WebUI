from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.deps import get_settings_dep
from backend.services import pdf as pdf_service
from tradingagents.storage import sqlite_history

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{ticker}/{trade_date}/pdf")
async def get_run_pdf(ticker: str, trade_date: str) -> Response:
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
        raise HTTPException(
            status_code=404, detail=f"final_state JSON missing at {json_path}"
        )
    final_state = json.loads(json_path.read_text(encoding="utf-8"))

    pdf_bytes = await asyncio.to_thread(
        pdf_service.generate_pdf, final_state, ticker, trade_date
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ticker}_{trade_date}.pdf"'
        },
    )
