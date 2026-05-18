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
        ftd = body["sections"]["final_trade_decision"]
        assert ftd["changed"] is True
        assert ftd["title"] == "最终投资决策"
        assert ftd["a_text"] == "BUY now"
        assert ftd["b_text"] == "SELL later"
        assert "BUY now" in ftd["diff"]
        assert "SELL later" in ftd["diff"]
        assert body["sections"]["market_report"]["changed"] is True


def test_diff_missing_run_returns_404(two_runs):
    with _client() as client:
        resp = client.get(
            "/api/history/TEST/2026-01-01/diff/GHOST/2099-01-01"
        )
        assert resp.status_code == 404
