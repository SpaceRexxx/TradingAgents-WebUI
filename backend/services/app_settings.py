from __future__ import annotations

import os
from pathlib import Path

from backend.deps import get_settings_dep

_RESULTS_DIR_ENV = "TRADINGAGENTS_RESULTS_DIR"


def _env_file_path() -> Path:
    """Resolve the .env path. Overridable via TRADINGAGENTS_ENV_FILE for tests.

    Mirrors backend.services.providers._env_file_path so both write the same
    file without coupling the two services.
    """
    override = os.environ.get("TRADINGAGENTS_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".env"


def get_results_dir() -> str:
    """Current results dir as Settings resolves it (env / .env / default)."""
    return str(get_settings_dep().results_dir)


def set_results_dir(path: str) -> str:
    """Persist results_dir to .env AND os.environ so subsequent
    get_settings() calls (uncached) pick it up immediately. Returns the
    stored value."""
    value = path.strip()

    env_path = _env_file_path()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

    new_line = f"{_RESULTS_DIR_ENV}={value}\n"
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{_RESULTS_DIR_ENV}="):
            lines[i] = new_line
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_line)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("".join(lines), encoding="utf-8")
    os.environ[_RESULTS_DIR_ENV] = value
    return value
