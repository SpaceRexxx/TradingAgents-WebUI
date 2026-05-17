import json

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import history as history_service
from tradingagents.storage import sqlite_history


def _write_log(results_dir, ticker, trade_date):
    log_dir = results_dir / ticker / "TradingAgentsStrategy_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"full_states_log_{trade_date}.json").write_text(
        json.dumps(
            {
                "company_of_interest": ticker,
                "trade_date": trade_date,
                "market_report": "m",
                "trader_investment_decision": "hold",
                "final_trade_decision": "BUY",
            }
        ),
        encoding="utf-8",
    )


def test_reindex_recovers_log_only_run(tmp_path):
    _write_log(tmp_path, "600039", "2026-05-17")
    assert not sqlite_history.query_analyses(tmp_path, ticker="600039")

    out = history_service.reindex(tmp_path)
    assert out == {"recovered": 1, "indexed": 1}

    report = tmp_path / "600039" / "2026-05-17" / "final_state_report.json"
    assert report.exists()
    data = json.loads(report.read_text())
    assert data["trader_investment_plan"] == "hold"
    rows = sqlite_history.query_analyses(tmp_path, ticker="600039")
    assert rows and rows[0]["trade_date"] == "2026-05-17"


def test_reindex_is_idempotent(tmp_path):
    _write_log(tmp_path, "AAA", "2026-05-16")
    history_service.reindex(tmp_path)
    out2 = history_service.reindex(tmp_path)
    assert out2 == {"recovered": 0, "indexed": 0}


def test_reindex_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    _write_log(tmp_path, "BBB", "2026-05-15")
    with TestClient(create_app()) as client:
        resp = client.post("/api/history/reindex")
        assert resp.status_code == 200
        assert resp.json() == {"recovered": 1, "indexed": 1}
        listed = client.get("/api/history").json()["items"]
    assert any(r["ticker"] == "BBB" for r in listed)
