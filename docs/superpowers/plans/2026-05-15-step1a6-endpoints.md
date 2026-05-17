# Step 1a.6 — Remaining Backend Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the backend's 15-endpoint surface from the original spec by adding the 4 deferred endpoint groups — diagnostics, providers (with strict API-key redaction), per-run PDF, and analysis diff — without touching `webapp.py` or `cli/`.

**Architecture:** Each group is an independent FastAPI router + a pure service module under `backend/services/`. Logic is ported (copied, not imported) from `webapp.py` because importing `webapp.py` triggers Streamlit side effects at module load. The canonical provider→env-var map (`tradingagents/llm_clients/api_key_env.py`) is reused as-is (it's a clean importable module). API keys are write-only over the wire: requests may submit a key, but no response or log ever echoes a key value.

**Tech Stack:** FastAPI, pytest, pytest-asyncio, `tradingagents.llm_clients.api_key_env`, `tradingagents.storage.sqlite_history`, Playwright (already used by the engine for PDF), Python 3.10+.

**Scope boundary:** ONLY the 4 deferred groups. **Deferred to Step 1b:** `webapp.py` → API-client migration. The 3 acknowledged Step 1a.5 residuals (handle leak, note/rating asymmetry, results-dir divergence) are NOT in scope here.

**Rollback:** `git reset --hard refs/tags/step-1a5-cleanup-complete` reverts to the Step 1a.5 milestone.

---

## File Structure

```
backend/services/diagnostics.py     # NEW: degraded-source detection (ported from webapp._detect_degraded_sources)
backend/services/providers.py       # NEW: provider list + key write + connection test
backend/services/pdf.py             # NEW: final_state -> PDF bytes (ported from webapp.generate_pdf_report)
backend/services/diff.py            # NEW: structured diff of two indexed analyses
backend/routes/diagnostics.py       # NEW: GET /api/diagnostics, POST /api/diagnostics/run
backend/routes/providers.py         # NEW: GET /api/providers, POST /{id}/key, POST /{id}/test
backend/routes/runs.py              # NEW: GET /api/runs/{ticker}/{trade_date}/pdf
backend/routes/history.py           # MODIFY: add GET /{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}
backend/schemas.py                  # MODIFY: add response/request models for the new endpoints
backend/main.py                     # MODIFY: register the 3 new routers

tests/backend/test_diagnostics_routes.py   # NEW
tests/backend/test_providers_routes.py     # NEW
tests/backend/test_pdf_routes.py           # NEW
tests/backend/test_diff_routes.py          # NEW
```

Endpoint identity decision: the original spec wrote `/api/runs/{id}/pdf` and `/api/history/{id}/diff/{otherId}` with opaque ids, but the indexed history is keyed by `(ticker, trade_date)` — there is no single opaque id. To stay consistent with the existing `PATCH /api/history/{ticker}/{trade_date}`, the new routes use `{ticker}/{trade_date}` path segments. This is a deliberate, documented deviation from the literal spec wording.

Tasks are independent and may run in any order, but the numbering reflects ascending risk (diagnostics simplest → providers most sensitive).

---

## Task 1: Diagnostics endpoints

`GET /api/diagnostics` and `POST /api/diagnostics/run` both return the degraded-source list. `_detect_degraded_sources` is stateless and cheap (a `shutil.which` + an import probe), so `run` simply re-evaluates and adds a UTC timestamp.

**Files:**
- Create: `backend/services/diagnostics.py`, `backend/routes/diagnostics.py`
- Create: `tests/backend/test_diagnostics_routes.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing test**

Create `tests/backend/test_diagnostics_routes.py`:

```python
from fastapi.testclient import TestClient

from backend.main import create_app


def _client():
    return TestClient(create_app())


def test_get_diagnostics_returns_list():
    with _client() as client:
        resp = client.get("/api/diagnostics")
        assert resp.status_code == 200
        body = resp.json()
        assert "degraded" in body
        assert isinstance(body["degraded"], list)


def test_run_diagnostics_returns_list_and_timestamp():
    with _client() as client:
        resp = client.post("/api/diagnostics/run")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["degraded"], list)
        assert "checked_at" in body and body["checked_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run (watchdog idiom — `pytest <args> > /tmp/o.log 2>&1 &` then poll PID ≤60s then `tail`):
`pytest tests/backend/test_diagnostics_routes.py -v`
Expected: FAIL — `/api/diagnostics` route does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/services/diagnostics.py` (ported verbatim from `webapp.py:106` `_detect_degraded_sources`, no Streamlit):

```python
from __future__ import annotations

import shutil


def detect_degraded_sources() -> list[str]:
    """Lightweight probe: which data sources are unavailable. Ported from
    webapp.py:_detect_degraded_sources (kept independent of Streamlit)."""
    degraded: list[str] = []
    if not shutil.which("opencli"):
        degraded.append("OpenCLI 未安装 → 雪球 / Reddit / 新浪 数据源不可用")
    try:
        import akshare  # noqa: F401
    except ImportError:
        degraded.append("akshare 未安装 → A 股数据源不可用（千股千评 / 公告 / 财联社）")
    return degraded
```

- [ ] **Step 4: Implement the router**

Create `backend/routes/diagnostics.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.diagnostics import detect_degraded_sources

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class DiagnosticsResponse(BaseModel):
    degraded: list[str]
    checked_at: str


@router.get("", response_model=DiagnosticsResponse)
def get_diagnostics() -> DiagnosticsResponse:
    return DiagnosticsResponse(
        degraded=detect_degraded_sources(),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/run", response_model=DiagnosticsResponse)
def run_diagnostics() -> DiagnosticsResponse:
    return DiagnosticsResponse(
        degraded=detect_degraded_sources(),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
```

(`GET` and `POST /run` are intentionally identical — detection is stateless. The split exists because the original spec lists both; `run` semantically means "re-check now" which for a stateless probe is the same call.)

- [ ] **Step 5: Register the router**

In `backend/main.py`, add `diagnostics` to the routes import line:

```python
from backend.routes import analysis, health, history, diagnostics
```

And after the existing `app.include_router(history.router)` line add:

```python
    app.include_router(diagnostics.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run (watchdog idiom): `pytest tests/backend/test_diagnostics_routes.py -v`
Expected: PASS (both). Then `pytest tests/backend/ -v` — all green (28 now: 26 + 2).

- [ ] **Step 7: Commit**

```bash
git add backend/services/diagnostics.py backend/routes/diagnostics.py backend/main.py tests/backend/test_diagnostics_routes.py
git commit -m "feat(backend): add diagnostics endpoints (Step 1a.6)"
```

---

## Task 2: Providers — list + key write (NO key ever returned)

`GET /api/providers` lists every provider from the canonical map with `configured` (env var set & non-empty) and `base_url`. `POST /api/providers/{id}/key` writes the key to `.env` AND `os.environ` (so it takes effect without restart) and returns ONLY `{id, configured: true}` — never the key, never a log line containing the key.

**Files:**
- Create: `backend/services/providers.py`, `backend/routes/providers.py`
- Create: `tests/backend/test_providers_routes.py`
- Modify: `backend/schemas.py`, `backend/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_providers_routes.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("DEEPSEEK_API_KEY=existing-value\n")
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(env))
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "existing-value")
    return env


def _client():
    return TestClient(create_app())


def test_list_providers_reports_configured_without_leaking_keys(env_file):
    with _client() as client:
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        items = {p["id"]: p for p in resp.json()["providers"]}
        assert items["deepseek"]["configured"] is True
        assert items["volcengine"]["configured"] is False
        # No response field may contain the actual key value.
        assert "existing-value" not in resp.text
        for p in items.values():
            assert "key" not in p  # only id/name/configured/base_url/env_var


def test_set_key_writes_env_and_marks_configured(env_file):
    with _client() as client:
        resp = client.post(
            "/api/providers/volcengine/key",
            json={"api_key": "ark-secret-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"id": "volcengine", "configured": True}
        assert "ark-secret-123" not in resp.text  # never echoed
    # .env now contains the new key line
    assert "ARK_API_KEY=ark-secret-123" in env_file.read_text()


def test_set_key_unknown_provider_returns_404(env_file):
    with _client() as client:
        resp = client.post("/api/providers/notaprovider/key", json={"api_key": "x"})
        assert resp.status_code == 404


def test_set_key_for_keyless_provider_returns_400(env_file):
    # ollama maps to None in PROVIDER_API_KEY_ENV — no key applicable
    with _client() as client:
        resp = client.post("/api/providers/ollama/key", json={"api_key": "x"})
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run (watchdog idiom): `pytest tests/backend/test_providers_routes.py -v`
Expected: FAIL — `/api/providers` does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/services/providers.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

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
}


def _env_file_path() -> Path:
    """Resolve the .env path. Overridable via TRADINGAGENTS_ENV_FILE for tests."""
    override = os.environ.get("TRADINGAGENTS_ENV_FILE")
    if override:
        return Path(override)
    # Repo-root .env, same location webapp.py:update_dotenv_file uses.
    return Path(__file__).resolve().parents[2] / ".env"


def list_providers() -> list[dict]:
    out: list[dict] = []
    for provider_id, env_var in sorted(PROVIDER_API_KEY_ENV.items()):
        if env_var is None:
            configured = True  # keyless (e.g. ollama) needs no key to "work"
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
    os.environ[env_var] = api_key  # take effect without a restart
```

- [ ] **Step 4: Add schemas**

In `backend/schemas.py`, append:

```python
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
```

(`BaseModel` and `Field` are already imported at the top of `schemas.py`.)

- [ ] **Step 5: Implement the router**

Create `backend/routes/providers.py`:

```python
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
```

(The connection-test endpoint is added in Task 3 to keep this task focused on the key-handling security surface.)

- [ ] **Step 6: Register the router**

In `backend/main.py`, add `providers` to the routes import and `app.include_router(providers.router)` after diagnostics.

- [ ] **Step 7: Run tests to verify they pass**

Run (watchdog idiom): `pytest tests/backend/test_providers_routes.py -v`
Expected: PASS (all 4). Then `pytest tests/backend/ -v` — all green (32 now: 28 + 4).

- [ ] **Step 8: Security self-check**

Run: `grep -rn "api_key\|API_KEY" backend/routes/providers.py backend/services/providers.py`
Confirm by reading: no `print`, no `logger`, no f-string that puts `api_key` into a response model field. The ONLY place `api_key` flows is into `.env` and `os.environ`. The response models (`SetKeyResponse`, `ProviderInfo`) contain no key field.

- [ ] **Step 9: Commit**

```bash
git add backend/services/providers.py backend/routes/providers.py backend/schemas.py backend/main.py tests/backend/test_providers_routes.py
git commit -m "feat(backend): add providers list + write-only key endpoint (Step 1a.6)"
```

---

## Task 3: Provider connection test

`POST /api/providers/{id}/test` performs a cheap reachability check. For OpenAI-compatible providers with a `base_url` and a configured key, it GETs `{base_url}/models` with a 5s timeout and a Bearer header. For keyless (ollama) it GETs `{base_url}/models` with no auth. For providers without a `base_url` (google/azure) or without a configured key, it returns a structured "skipped"/"not configured" result rather than a hard failure.

**Files:**
- Modify: `backend/services/providers.py`, `backend/routes/providers.py`, `backend/schemas.py`
- Modify: `tests/backend/test_providers_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/backend/test_providers_routes.py`:

```python
def test_test_provider_not_configured_returns_ok_false(env_file, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with _client() as client:
        resp = client.post("/api/providers/volcengine/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "volcengine"
        assert body["ok"] is False
        assert body["reason"] == "not_configured"


def test_test_provider_reachable(env_file, monkeypatch):
    # Stub the HTTP probe so the test is offline-deterministic.
    from backend.services import providers as ps

    monkeypatch.setattr(ps, "_probe_models_endpoint", lambda url, key: (True, 200))
    with _client() as client:
        resp = client.post("/api/providers/deepseek/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"id": "deepseek", "ok": True, "reason": "reachable", "status": 200}


def test_test_provider_unreachable(env_file, monkeypatch):
    from backend.services import providers as ps

    monkeypatch.setattr(ps, "_probe_models_endpoint", lambda url, key: (False, 0))
    with _client() as client:
        resp = client.post("/api/providers/deepseek/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "unreachable"


def test_test_unknown_provider_returns_404(env_file):
    with _client() as client:
        resp = client.post("/api/providers/nope/test")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run (watchdog idiom): `pytest tests/backend/test_providers_routes.py -v`
Expected: the 4 new tests FAIL — `/test` route does not exist. The Task 2 tests still pass.

- [ ] **Step 3: Add the probe + test logic to the service**

Append to `backend/services/providers.py`:

```python
import httpx


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
        # google/azure/etc. — no OpenAI-compatible /models probe available.
        return {"id": provider_id, "ok": True, "reason": "skipped_no_base_url"}

    ok, status = _probe_models_endpoint(base_url, key)
    return {
        "id": provider_id,
        "ok": ok,
        "reason": "reachable" if ok else "unreachable",
        "status": status,
    }
```

- [ ] **Step 4: Add schema + route**

In `backend/schemas.py`, append:

```python
class TestProviderResponse(BaseModel):
    id: str
    ok: bool
    reason: str
    status: int | None = None
```

In `backend/routes/providers.py`, add `TestProviderResponse` to the existing `from backend.schemas import (...)` block and append the route:

```python
@router.post("/{provider_id}/test", response_model=TestProviderResponse)
def test_provider(provider_id: str) -> TestProviderResponse:
    try:
        result = provider_service.test_provider(provider_id)
    except provider_service.UnknownProvider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    return TestProviderResponse(**result)
```

- [ ] **Step 5: Run tests to verify they pass**

Run (watchdog idiom): `pytest tests/backend/test_providers_routes.py -v`
Expected: PASS (all 8 — 4 from Task 2 + 4 new). Then `pytest tests/backend/ -v` — all green (36 now: 32 + 4).

- [ ] **Step 6: Commit**

```bash
git add backend/services/providers.py backend/routes/providers.py backend/schemas.py tests/backend/test_providers_routes.py
git commit -m "feat(backend): add provider connection-test endpoint (Step 1a.6)"
```

---

## Task 4: Per-run PDF endpoint

`GET /api/runs/{ticker}/{trade_date}/pdf` looks up the indexed analysis, reads its stored `final_state` JSON, generates a PDF via a ported `generate_pdf_report` (Playwright in a subprocess — already the engine's pattern), and streams it back as `application/pdf`.

**Files:**
- Create: `backend/services/pdf.py`, `backend/routes/runs.py`
- Create: `tests/backend/test_pdf_routes.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing test**

Create `tests/backend/test_pdf_routes.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch):
    d = tmp_path / "TEST" / "2026-01-01"
    d.mkdir(parents=True)
    (d / "final_state_report.json").write_text(
        json.dumps(
            {
                "company_of_interest": "TEST",
                "trade_date": "2026-01-01",
                "market_report": "# Market\nstrong",
                "final_trade_decision": "BUY",
            }
        )
    )
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    from tradingagents.storage import sqlite_history

    sqlite_history.rebuild_from_disk(tmp_path)
    return tmp_path


def _client():
    return TestClient(create_app())


def test_pdf_unknown_run_returns_404(seeded):
    with _client() as client:
        resp = client.get("/api/runs/GHOST/2099-01-01/pdf")
        assert resp.status_code == 404


def test_pdf_known_run_returns_pdf_bytes(seeded, monkeypatch):
    # Stub the Playwright subprocess so the test is offline + fast.
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(
        pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 fake bytes"
    )
    with _client() as client:
        resp = client.get("/api/runs/TEST/2026-01-01/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
```

- [ ] **Step 2: Run test to verify it fails**

Run (watchdog idiom): `pytest tests/backend/test_pdf_routes.py -v`
Expected: FAIL — route does not exist.

- [ ] **Step 3: Implement the PDF service**

Create `backend/services/pdf.py` (HTML build ported from `webapp.py:992` `generate_pdf_report`; the Playwright subprocess is isolated into `_render_pdf` so tests can stub it):

```python
from __future__ import annotations

import subprocess
import sys

import markdown2

_SECTIONS = [
    ("第一阶段：分析师团队报告", [
        ("market_report", "市场分析报告"),
        ("news_report", "新闻分析报告"),
        ("sentiment_report", "社交情绪报告"),
        ("fundamentals_report", "基本面分析报告"),
    ]),
    ("第二阶段：研究团队决策", [("investment_plan", "")]),
    ("第三阶段：交易团队计划", [("trader_investment_plan", "")]),
    ("第四/五阶段：风险管理与最终决策", [("final_trade_decision", "")]),
]

_CSS = (
    "body { font-family: sans-serif; font-size: 10pt; line-height: 1.6; } "
    "h1 { font-size: 22pt; color: #1E293B; text-align: center; } "
    "h2 { font-size: 16pt; color: #334155; border-bottom: 2px solid #f1f5f9; "
    "padding-bottom: 6px; margin-top: 25px;} "
    "h3 { font-size: 13pt; color: #475569; margin-top: 20px;} "
    "table { border-collapse: collapse; width: 100%; margin-top: 15px; } "
    "th, td { border: 1px solid #e2e8f0; text-align: left; padding: 8px; } "
    "th { background-color: #f8fafc; font-weight: bold; }"
)

_RENDER_SCRIPT = """
import sys
from playwright.sync_api import sync_playwright

html = sys.stdin.read()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    pdf_bytes = page.pdf(format="A4", margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"})
    browser.close()
    sys.stdout.buffer.write(pdf_bytes)
"""


def _build_html(final_state: dict, ticker: str, trade_date: str) -> str:
    parts = [f"<h1>{ticker} 交易分析报告</h1>",
             f"<p><b>分析日期:</b> {trade_date}</p><hr>"]
    for section_title, keys in _SECTIONS:
        chunk = []
        for key, sub_title in keys:
            val = final_state.get(key)
            if val:
                html_md = markdown2.markdown(
                    val, extras=["tables", "fenced-code-blocks", "header-ids"]
                )
                chunk.append(f"<h3>{sub_title}</h3>{html_md}" if sub_title else html_md)
        if chunk:
            parts.append(f"<h2>{section_title}</h2>" + "\n".join(chunk))
    body = "\n".join(parts)
    return f"<html><head><meta charset='UTF-8'><style>{_CSS}</style></head><body>{body}</body></html>"


def _render_pdf(html: str) -> bytes:
    """Run Playwright in a subprocess (avoids event-loop conflicts). Stubbed in tests."""
    proc = subprocess.run(
        [sys.executable, "-c", _RENDER_SCRIPT],
        input=html.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore"))
    return proc.stdout


def generate_pdf(final_state: dict, ticker: str, trade_date: str) -> bytes:
    return _render_pdf(_build_html(final_state, ticker, trade_date))
```

- [ ] **Step 4: Implement the runs router**

Create `backend/routes/runs.py`:

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.deps import get_settings_dep
from backend.services import pdf as pdf_service
from tradingagents.storage import sqlite_history

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{ticker}/{trade_date}/pdf")
async def get_run_pdf(ticker: str, trade_date: str) -> Response:
    settings = get_settings_dep()
    rows = sqlite_history.query_analyses(settings.results_dir, ticker=ticker)
    match = next((r for r in rows if r["trade_date"] == trade_date), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"No indexed analysis for {ticker} {trade_date}",
        )

    json_path = Path(match["json_path"])
    if not json_path.exists():
        raise HTTPException(
            status_code=404, detail=f"final_state JSON missing at {json_path}"
        )
    final_state = json.loads(json_path.read_text(encoding="utf-8"))

    pdf_bytes = await asyncio.to_thread(
        pdf_service.generate_pdf, final_state, ticker, trade_date
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ticker}_{trade_date}.pdf"'
        },
    )
```

- [ ] **Step 5: Register the router**

In `backend/main.py`, add `runs` to the routes import and `app.include_router(runs.router)` after providers.

- [ ] **Step 6: Run test to verify it passes**

Run (watchdog idiom): `pytest tests/backend/test_pdf_routes.py -v`
Expected: PASS (both). Then `pytest tests/backend/ -v` — all green (38 now: 36 + 2).

- [ ] **Step 7: Commit**

```bash
git add backend/services/pdf.py backend/routes/runs.py backend/main.py tests/backend/test_pdf_routes.py
git commit -m "feat(backend): add per-run PDF endpoint (Step 1a.6)"
```

---

## Task 5: Analysis diff endpoint

`GET /api/history/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}` loads both indexed analyses' `final_state` JSON and returns a per-section unified text diff plus a presence map.

**Files:**
- Create: `backend/services/diff.py`
- Create: `tests/backend/test_diff_routes.py`
- Modify: `backend/routes/history.py`, `backend/schemas.py`

- [ ] **Step 1: Write failing test**

Create `tests/backend/test_diff_routes.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def two_runs(tmp_path: Path, monkeypatch):
    for tk, dt, decision in [("TEST", "2026-01-01", "BUY now"),
                             ("TEST", "2026-02-01", "SELL later")]:
        d = tmp_path / tk / dt
        d.mkdir(parents=True)
        (d / "final_state_report.json").write_text(json.dumps({
            "company_of_interest": tk, "trade_date": dt,
            "market_report": f"market for {dt}",
            "final_trade_decision": decision,
        }))
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    from tradingagents.storage import sqlite_history
    sqlite_history.rebuild_from_disk(tmp_path)
    return tmp_path


def _client():
    return TestClient(create_app())


def test_diff_two_known_runs(two_runs):
    with _client() as client:
        resp = client.get(
            "/api/history/TEST/2026-01-01/diff/TEST/2026-02-01"
        )
        assert resp.status_code == 200
        body = resp.json()
        # final_trade_decision changed -> appears in the section diff
        ftd = body["sections"]["final_trade_decision"]
        assert ftd["changed"] is True
        assert "BUY now" in ftd["diff"]
        assert "SELL later" in ftd["diff"]
        # market_report changed too
        assert body["sections"]["market_report"]["changed"] is True


def test_diff_missing_run_returns_404(two_runs):
    with _client() as client:
        resp = client.get(
            "/api/history/TEST/2026-01-01/diff/GHOST/2099-01-01"
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run (watchdog idiom): `pytest tests/backend/test_diff_routes.py -v`
Expected: FAIL — diff route does not exist.

- [ ] **Step 3: Implement the diff service**

Create `backend/services/diff.py`:

```python
from __future__ import annotations

import difflib
import json
from pathlib import Path

from tradingagents.storage import sqlite_history

_DIFF_KEYS = [
    "market_report",
    "news_report",
    "sentiment_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
]


class AnalysisNotFound(Exception):
    pass


def _load_final_state(results_dir, ticker: str, trade_date: str) -> dict:
    rows = sqlite_history.query_analyses(results_dir, ticker=ticker)
    match = next((r for r in rows if r["trade_date"] == trade_date), None)
    if match is None:
        raise AnalysisNotFound(f"{ticker} {trade_date}")
    p = Path(match["json_path"])
    if not p.exists():
        raise AnalysisNotFound(f"{ticker} {trade_date} (json missing)")
    return json.loads(p.read_text(encoding="utf-8"))


def diff_analyses(
    results_dir,
    ticker_a: str,
    date_a: str,
    ticker_b: str,
    date_b: str,
) -> dict:
    a = _load_final_state(results_dir, ticker_a, date_a)
    b = _load_final_state(results_dir, ticker_b, date_b)

    sections: dict[str, dict] = {}
    for key in _DIFF_KEYS:
        va = (a.get(key) or "").strip()
        vb = (b.get(key) or "").strip()
        changed = va != vb
        diff_text = ""
        if changed:
            diff_text = "\n".join(
                difflib.unified_diff(
                    va.splitlines(),
                    vb.splitlines(),
                    fromfile=f"{ticker_a}@{date_a}:{key}",
                    tofile=f"{ticker_b}@{date_b}:{key}",
                    lineterm="",
                )
            )
        sections[key] = {"changed": changed, "diff": diff_text}

    return {
        "a": {"ticker": ticker_a, "trade_date": date_a},
        "b": {"ticker": ticker_b, "trade_date": date_b},
        "sections": sections,
    }
```

- [ ] **Step 4: Add schema + route**

In `backend/schemas.py`, append:

```python
class DiffSide(BaseModel):
    ticker: str
    trade_date: str


class DiffSection(BaseModel):
    changed: bool
    diff: str


class DiffResponse(BaseModel):
    a: DiffSide
    b: DiffSide
    sections: dict[str, DiffSection]
```

In `backend/routes/history.py`, add to the imports:

```python
from backend.schemas import DiffResponse
from backend.services import diff as diff_service
```

(merge with the existing `from backend.schemas import ...` line rather than duplicating it; `HTTPException` and `get_settings_dep` are already imported in `history.py` from Step 1a.5 Task 6). Append the route to the existing `router` in `history.py`:

```python
@router.get(
    "/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}",
    response_model=DiffResponse,
)
def diff_history(
    ticker: str,
    trade_date: str,
    other_ticker: str,
    other_trade_date: str,
) -> DiffResponse:
    settings = get_settings_dep()
    try:
        result = diff_service.diff_analyses(
            settings.results_dir, ticker, trade_date, other_ticker, other_trade_date
        )
    except diff_service.AnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DiffResponse(**result)
```

Note: this route is on the existing `history` router (prefix `/api/history`), full path `/api/history/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}`. The GET method does not collide with the existing `PATCH /{ticker}/{trade_date}` (different verb + more path segments). Declare it AFTER the existing PATCH for tidiness.

- [ ] **Step 5: Run test to verify it passes**

Run (watchdog idiom): `pytest tests/backend/test_diff_routes.py -v`
Expected: PASS (both). Then `pytest tests/backend/ -v` — all green (40 now: 38 + 2).

- [ ] **Step 6: Commit**

```bash
git add backend/services/diff.py backend/routes/history.py backend/schemas.py tests/backend/test_diff_routes.py
git commit -m "feat(backend): add analysis diff endpoint (Step 1a.6)"
```

---

## Task 6: Final verification + docs + tag

- [ ] **Step 1: Full backend suite**

Run (watchdog idiom): `pytest tests/backend/ -v`
Expected: ALL pass (~40 = the 26 from Step 1a.5 + the new ones).

- [ ] **Step 2: No regression in existing tests**

Run: `pytest tests/ --ignore=tests/backend -q --no-header`
Expected: exactly the 6 known pre-existing failures (`test_env_overrides.py` ×2, `test_memory_log.py` ×2, `test_structured_agents.py` ×2). NO new failures.

- [ ] **Step 3: Streamlit still launches**

Start `streamlit run webapp.py --server.headless true --server.port 8505` ~8s, confirm "You can now view your Streamlit app", kill it. No new errors (we did NOT modify webapp.py).

- [ ] **Step 4: Security grep — no key leakage anywhere**

Run: `grep -rn "api_key\|API_KEY\|secret" backend/ --include="*.py" | grep -iv test`
Read each hit. Confirm: keys flow ONLY into `.env`/`os.environ` (providers service). No `print`, no `logger.*` with a key, no response model carrying a key value.

- [ ] **Step 5: Update docs/backend.md**

In `docs/backend.md`, in the "Endpoints (Step 1a)" table, add rows for the new endpoints:

```markdown
| GET | `/api/diagnostics` | `{degraded: string[], checked_at}` data-source health |
| POST | `/api/diagnostics/run` | Re-check; same shape as GET |
| GET | `/api/providers` | List providers with `configured` (never the key) |
| POST | `/api/providers/{id}/key` | Body `{api_key}`. Writes .env + os.environ. Returns `{id, configured}`. 404 unknown, 400 keyless |
| POST | `/api/providers/{id}/test` | Reachability probe. `{id, ok, reason, status?}` |
| GET | `/api/runs/{ticker}/{trade_date}/pdf` | Streams `application/pdf`. 404 if not indexed |
| GET | `/api/history/{ticker}/{trade_date}/diff/{other_ticker}/{other_trade_date}` | Per-section unified diff. 404 if either side missing |
```

And change the "Endpoints deferred to Step 1a.6" line to:

```markdown
All originally-deferred endpoints are now implemented. Remaining work: **Step 1b** — `webapp.py` → API-client migration.
```

- [ ] **Step 6: Commit + tag**

```bash
git add docs/backend.md
git commit -m "docs(backend): document Step 1a.6 endpoints"
git tag -a step-1a6-endpoints-complete -m "Step 1a.6 — diagnostics/providers/pdf/diff endpoints; backend API surface complete"
```

- [ ] **Step 7: Report the commit range**

Run: `git log --oneline refs/tags/step-1a5-cleanup-complete..HEAD`
Expected: ~6 commits (Tasks 1-5 + docs), all on `main`.

---

## Self-Review (plan author)

**Spec coverage:** Original deferred set = providers (GET/test/key), diagnostics (GET/run), runs pdf, history diff. Mapped: Task 1 = diagnostics ×2; Task 2 = providers GET + key; Task 3 = providers test; Task 4 = runs pdf; Task 5 = history diff. All covered. Path-identity deviation (`{ticker}/{trade_date}` instead of opaque `{id}`) documented in File Structure.

**Placeholder scan:** No TBD/TODO/"similar to". Every code step shows full file/edit content. Playwright + httpx probes are isolated behind `_render_pdf`/`_probe_models_endpoint` so tests stub them (no network/subprocess in CI).

**Type consistency:**
- `provider_service` API: `list_providers() -> list[dict]`, `set_key(id, key)` raising `UnknownProvider`/`ProviderNeedsNoKey`, `test_provider(id) -> dict` raising `UnknownProvider`, `_probe_models_endpoint(url, key) -> (bool,int)` — consistent across Tasks 2 & 3 and their tests (tests monkeypatch `ps._probe_models_endpoint`).
- `pdf_service`: `generate_pdf(final_state, ticker, trade_date) -> bytes`, `_render_pdf(html) -> bytes` (test stubs `_render_pdf`) — consistent Task 4.
- `diff_service`: `diff_analyses(results_dir, ticker_a, date_a, ticker_b, date_b) -> dict` raising `AnalysisNotFound`; response keys `a/b/sections` with `sections[k] = {changed, diff}` — matches `DiffResponse` schema and the Task 5 test assertions.
- Schemas appended to `backend/schemas.py` (ProviderInfo/ProviderListResponse/SetKeyRequest/SetKeyResponse/TestProviderResponse/DiffSide/DiffSection/DiffResponse) referenced consistently by their routers.
- Router registration: `main.py` gains diagnostics (Task 1), providers (Task 2), runs (Task 4); diff is added to the existing `history` router (Task 5), so no new registration for it.

**Security invariant:** Tasks 2/3 + the Task 6 grep enforce that API keys never appear in any response model, log, or print — only `.env` + `os.environ`. Tests explicitly assert the key string is absent from `resp.text`.
