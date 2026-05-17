from __future__ import annotations

import os
from pathlib import Path

from backend.deps import get_settings_dep

_RESULTS_DIR_ENV = "TRADINGAGENTS_RESULTS_DIR"

# Settings-field -> TRADINGAGENTS_* env var. These map to default_config
# keys of the same name and are re-applied per run (see runner factory).
_LLM_ENV = {
    "llm_provider": "TRADINGAGENTS_LLM_PROVIDER",
    "deep_think_llm": "TRADINGAGENTS_DEEP_THINK_LLM",
    "quick_think_llm": "TRADINGAGENTS_QUICK_THINK_LLM",
    "backend_url": "TRADINGAGENTS_LLM_BACKEND_URL",
}


def _env_file_path() -> Path:
    """Resolve the .env path. Overridable via TRADINGAGENTS_ENV_FILE for tests.

    Mirrors backend.services.providers._env_file_path so both write the same
    file without coupling the two services.
    """
    override = os.environ.get("TRADINGAGENTS_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".env"


def _upsert_env(env_var: str, value: str) -> str:
    """Upsert `env_var=value` into .env AND os.environ. Returns stored value."""
    value = value.strip()
    env_path = _env_file_path()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

    new_line = f"{env_var}={value}\n"
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

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("".join(lines), encoding="utf-8")
    os.environ[env_var] = value
    return value


def get_results_dir() -> str:
    """Current results dir as Settings resolves it (env / .env / default)."""
    return str(get_settings_dep().results_dir)


def set_results_dir(path: str) -> str:
    """Persist results_dir to .env + os.environ (get_settings is uncached)."""
    return _upsert_env(_RESULTS_DIR_ENV, path)


def get_llm_settings() -> dict[str, str]:
    """Effective LLM provider/models, with TRADINGAGENTS_* env applied on a
    fresh DEFAULT_CONFIG copy (import-time DEFAULT_CONFIG is frozen)."""
    from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides

    cfg = _apply_env_overrides(dict(DEFAULT_CONFIG))
    return {k: str(cfg.get(k, "")) for k in _LLM_ENV}


def set_llm_settings(values: dict[str, str | None]) -> dict[str, str]:
    """Persist any provided LLM fields to .env + os.environ; takes effect for
    new analyses (runner re-applies env per run). Returns effective settings."""
    for field, env_var in _LLM_ENV.items():
        v = values.get(field)
        if v is not None and str(v).strip() != "":
            _upsert_env(env_var, str(v))
    return get_llm_settings()
