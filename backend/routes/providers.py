from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    ProviderListResponse,
    SetKeyRequest,
    SetKeyResponse,
)
from backend.services import providers as provider_service

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=ProviderListResponse)
def list_providers() -> ProviderListResponse:
    return ProviderListResponse(providers=provider_service.list_providers())


@router.post("/{provider_id}/key", response_model=SetKeyResponse)
def set_key(provider_id: str, body: SetKeyRequest) -> SetKeyResponse:
    try:
        provider_service.set_key(provider_id, body.api_key)
    except provider_service.UnknownProvider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    except provider_service.ProviderNeedsNoKey:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {provider_id} does not use an API key",
        )
    return SetKeyResponse(id=provider_id, configured=True)
