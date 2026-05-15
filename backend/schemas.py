from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    trade_date: str = Field(..., description="YYYY-MM-DD")
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class StartAnalysisResponse(BaseModel):
    run_id: str


class AbortResponse(BaseModel):
    run_id: str
    accepted: bool


class ProviderInfo(BaseModel):
    id: str
    name: str
    env_var: str | None
    base_url: str | None
    configured: bool


class ProviderListResponse(BaseModel):
    providers: list[ProviderInfo]


class SetKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class SetKeyResponse(BaseModel):
    id: str
    configured: bool
