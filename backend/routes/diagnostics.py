from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.diagnostics import detect_degraded_sources

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class DiagnosticsResponse(BaseModel):
    degraded: list[str]
    checked_at: str


@router.get("", response_model=DiagnosticsResponse)
def get_diagnostics() -> DiagnosticsResponse:
    return DiagnosticsResponse(
        degraded=detect_degraded_sources(),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/run", response_model=DiagnosticsResponse)
def run_diagnostics() -> DiagnosticsResponse:
    return DiagnosticsResponse(
        degraded=detect_degraded_sources(),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
