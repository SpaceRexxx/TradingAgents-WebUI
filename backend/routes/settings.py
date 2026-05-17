from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import SettingsResponse, UpdateSettingsRequest
from backend.services import app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return SettingsResponse(results_dir=app_settings.get_results_dir())


@router.put("", response_model=SettingsResponse)
def update_settings(body: UpdateSettingsRequest) -> SettingsResponse:
    stored = app_settings.set_results_dir(body.results_dir)
    return SettingsResponse(results_dir=stored)
