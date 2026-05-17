from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.deps import get_settings_dep
from backend.services.token_stats import load_cumulative

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/cumulative")
def cumulative() -> dict[str, Any]:
    """Aggregate token / cost / tool-call stats across all analyses.

    Reads {results_dir}/cumulative_stats.json (zeros when absent).
    """
    settings = get_settings_dep()
    return load_cumulative(settings.results_dir)
