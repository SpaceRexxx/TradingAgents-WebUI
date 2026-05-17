from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    from tradingagents.default_config import DEFAULT_CONFIG

    return {
        "status": "ok",
        "model": str(DEFAULT_CONFIG.get("deep_think_llm", "")),
        "provider": str(DEFAULT_CONFIG.get("llm_provider", "")),
    }
