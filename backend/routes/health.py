from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides

    cfg = _apply_env_overrides(dict(DEFAULT_CONFIG))
    return {
        "status": "ok",
        "model": str(cfg.get("deep_think_llm", "")),
        "provider": str(cfg.get("llm_provider", "")),
    }
