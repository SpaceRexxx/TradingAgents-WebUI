from __future__ import annotations

import os
from pathlib import Path

import httpx

from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV

# base_url per provider, mirrored from cli/utils.py:select_llm_provider's
# PROVIDERS table. Kept here (not imported) because cli/utils defines it
# inside a function. Providers absent from this map have base_url=None.
_BASE_URL: dict[str, str | None] = {
    "openai": "https://api.openai.com/v1",
    "google": None,
    "anthropic": "https://api.anthropic.com/",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4/",
    "minimax": "https://api.minimax.io/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "azure": None,
    "ollama": "http://localhost:11434/v1",
    # Volcengine Ark OpenAI-compatible inference endpoint.
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}


def _env_file_path() -> Path:
    """Resolve the .env path. Overridable via TRADINGAGENTS_ENV_FILE for tests."""
    override = os.environ.get("TRADINGAGENTS_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".env"


def list_providers() -> list[dict]:
    out: list[dict] = []
    for provider_id, env_var in sorted(PROVIDER_API_KEY_ENV.items()):
        if env_var is None:
            configured = True
        else:
            configured = bool(os.environ.get(env_var, "").strip())
        out.append(
            {
                "id": provider_id,
                "name": provider_id,
                "env_var": env_var,
                "base_url": _BASE_URL.get(provider_id),
                "configured": configured,
            }
        )
    return out


class UnknownProvider(Exception):
    pass


class ProviderNeedsNoKey(Exception):
    pass


def set_key(provider_id: str, api_key: str) -> None:
    """Persist `api_key` for `provider_id` to .env AND os.environ.

    Raises UnknownProvider if the id is not in the canonical map, or
    ProviderNeedsNoKey if the provider maps to None (e.g. ollama).
    NEVER logs or returns the key.
    """
    if provider_id not in PROVIDER_API_KEY_ENV:
        raise UnknownProvider(provider_id)
    env_var = PROVIDER_API_KEY_ENV[provider_id]
    if env_var is None:
        raise ProviderNeedsNoKey(provider_id)

    env_path = _env_file_path()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

    new_line = f"{env_var}={api_key}\n"
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{env_var}="):
            lines[i] = new_line
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_line)

    env_path.write_text("".join(lines), encoding="utf-8")
    os.environ[env_var] = api_key


def _probe_models_endpoint(base_url: str, api_key: str | None) -> tuple[bool, int]:
    """GET {base_url}/models with a short timeout. Returns (ok, status_code).
    ok is True only on HTTP 2xx. Network failure -> (False, 0)."""
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = httpx.get(url, headers=headers, timeout=5.0)
        return (200 <= resp.status_code < 300, resp.status_code)
    except httpx.HTTPError:
        return (False, 0)


def test_provider(provider_id: str) -> dict:
    """Reachability check. Returns {id, ok, reason, status?}.
    Raises UnknownProvider for an unknown id."""
    if provider_id not in PROVIDER_API_KEY_ENV:
        raise UnknownProvider(provider_id)

    env_var = PROVIDER_API_KEY_ENV[provider_id]
    base_url = _BASE_URL.get(provider_id)
    key = None if env_var is None else os.environ.get(env_var, "").strip()

    if env_var is not None and not key:
        return {"id": provider_id, "ok": False, "reason": "not_configured"}
    if not base_url:
        return {"id": provider_id, "ok": True, "reason": "skipped_no_base_url"}

    ok, status = _probe_models_endpoint(base_url, key)
    return {
        "id": provider_id,
        "ok": ok,
        "reason": "reachable" if ok else "unreachable",
        "status": status,
    }
