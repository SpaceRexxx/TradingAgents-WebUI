from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import get_settings_dep
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
    q: str | None = None,
) -> HistoryListResponse:
    settings = get_settings_dep()
    items = history_service.list_analyses(settings.results_dir, ticker=ticker, query=q)
    return HistoryListResponse(items=items)


@router.patch("/{ticker}/{trade_date}")
def patch_history(ticker: str, trade_date: str, body: PatchHistoryRequest) -> dict:
    settings = get_settings_dep()
    if body.note is not None:
        history_service.set_note(settings.results_dir, ticker, trade_date, body.note)
    if body.rating is not None:
        try:
            history_service.set_rating(settings.results_dir, ticker, trade_date, body.rating)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
    return {"ticker": ticker, "trade_date": trade_date, "updated": True}
