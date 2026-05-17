from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import SettingsResponse, UpdateSettingsRequest
from backend.services import app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current() -> SettingsResponse:
    return SettingsResponse(
        results_dir=app_settings.get_results_dir(),
        **app_settings.get_llm_settings(),
    )


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _current()


@router.put("", response_model=SettingsResponse)
def update_settings(body: UpdateSettingsRequest) -> SettingsResponse:
    if body.results_dir is not None:
        app_settings.set_results_dir(body.results_dir)
    app_settings.set_llm_settings(
        {
            "llm_provider": body.llm_provider,
            "deep_think_llm": body.deep_think_llm,
            "quick_think_llm": body.quick_think_llm,
            "backend_url": body.backend_url,
        }
    )
    return _current()
