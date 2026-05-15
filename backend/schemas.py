from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("api_key")
    @classmethod
    def _no_newlines(cls, v: str) -> str:
        # Prevent .env injection: a key containing a newline would write a
        # second attacker-controlled KEY=value line into the .env file.
        if "\n" in v or "\r" in v:
            raise ValueError("API key must not contain newline characters")
        return v


class SetKeyResponse(BaseModel):
    id: str
    configured: bool
