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
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(
        pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 fake bytes"
    )
    with _client() as client:
        resp = client.get("/api/runs/TEST/2026-01-01/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")


def test_pdf_content_disposition_is_sanitized(tmp_path, monkeypatch):
    # A ticker containing a double-quote must not break/inject the
    # Content-Disposition header's filename="..." quoting.
    evil = 'AA"X'
    d = tmp_path / evil / "2026-01-01"
    d.mkdir(parents=True)
    (d / "final_state_report.json").write_text(
        json.dumps({"company_of_interest": evil, "trade_date": "2026-01-01",
                    "final_trade_decision": "BUY"})
    )
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    from tradingagents.storage import sqlite_history

    sqlite_history.rebuild_from_disk(tmp_path)

    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 x")
    with _client() as client:
        resp = client.get(f'/api/runs/{evil}/2026-01-01/pdf')
        assert resp.status_code == 200
        cd = resp.headers["content-disposition"]
        # The raw double-quote from the ticker must be gone; only the
        # surrounding filename="" quotes remain.
        assert cd == 'inline; filename="AA_X_2026-01-01.pdf"'
