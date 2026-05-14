from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from backend.deps import get_registry
from backend.schemas import AbortResponse, StartAnalysisRequest, StartAnalysisResponse
from backend.services.registry import RunRegistry
from backend.services.runner import AnalysisRequest, start_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/start", response_model=StartAnalysisResponse)
async def start(
    body: StartAnalysisRequest,
    registry: RunRegistry = Depends(get_registry),
) -> StartAnalysisResponse:
    handle = await start_analysis(
        AnalysisRequest(
            ticker=body.ticker,
            trade_date=body.trade_date,
            config_overrides=body.config_overrides,
        ),
        registry,
    )
    return StartAnalysisResponse(run_id=handle.run_id)


@router.post("/{run_id}/abort", response_model=AbortResponse)
async def abort(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> AbortResponse:
    handle = registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    handle.cancel_event.set()
    return AbortResponse(run_id=run_id, status=handle.status.value)


@router.websocket("/ws/{run_id}")
async def stream(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    registry: RunRegistry = websocket.app.state.registry
    handle = registry.get(run_id)
    if handle is None:
        await websocket.close(code=4404)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(handle.queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            await websocket.send_text(json.dumps(event, default=str))
            if event["type"] in {"done", "aborted", "error"}:
                break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
