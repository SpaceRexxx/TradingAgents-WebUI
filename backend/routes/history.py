from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import get_settings_dep
from backend.schemas import DiffResponse
from backend.services import diff as diff_service
from backend.services import history as history_service

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryListResponse(BaseModel):
    items: list[dict]


class PatchHistoryRequest(BaseModel):
    note: str | None = None
    rating: str | None = None


@router.get("", response_model=HistoryListResponse)
def list_history(
    ticker: str | None = None,
) -> HistoryListResponse:
    settings = get_settings_dep()
    items = history_service.list_analyses(settings.results_dir, ticker=ticker)
    return HistoryListResponse(items=items)


@router.post("/reindex")
def reindex_history() -> dict:
    settings = get_settings_dep()
    return history_service.reindex(settings.results_dir)


@router.patch("/{ticker}/{trade_date}")
def patch_history(ticker: str, trade_date: str, body: PatchHistoryRequest) -> dict:
    settings = get_settings_dep()
    if body.note is not None:
        history_service.set_note(settings.results_dir, ticker, trade_date, body.note)
    if body.rating is not None:
        updated = history_service.set_rating(
            settings.results_dir, ticker, trade_date, body.rating
        )
        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"No indexed analysis for {ticker} {trade_date}",
            )
    return {"ticker": ticker, "trade_date": trade_date, "updated": True}


@router.get(
    "/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}",
    response_model=DiffResponse,
)
def diff_history(
    ticker: str,
    trade_date: str,
    other_ticker: str,
    other_trade_date: str,
) -> DiffResponse:
    settings = get_settings_dep()
    try:
        result = diff_service.diff_analyses(
            settings.results_dir, ticker, trade_date, other_ticker, other_trade_date
        )
    except diff_service.AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DiffResponse(**result)
