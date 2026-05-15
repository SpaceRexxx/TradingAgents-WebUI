import json
from pathlib import Path

from backend.services.persistence import persist_run


def test_persist_run_writes_json_and_indexes(tmp_path: Path):
    final_state = {
        "company_of_interest": "TEST",
        "trade_date": "2026-01-01",
        "final_trade_decision": "BUY: strong",
        "market_report": "m",
        "messages": ["should-be-dropped"],
    }

    persist_run(
        results_dir=tmp_path,
        ticker="TEST",
        trade_date="2026-01-01",
        final_state=final_state,
        model="deepseek-chat",
        provider="DeepSeek",
    )

    json_file = tmp_path / "TEST" / "2026-01-01" / "final_state_report.json"
    assert json_file.exists()
    saved = json.loads(json_file.read_text())
    assert "messages" not in saved
    assert saved["final_trade_decision"] == "BUY: strong"

    from tradingagents.storage import sqlite_history

    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert rows and rows[0]["ticker"] == "TEST"
    assert rows[0]["json_path"] == str(json_file)


def test_persist_run_is_idempotent(tmp_path: Path):
    fs = {"company_of_interest": "TEST", "trade_date": "2026-01-01",
          "final_trade_decision": "HOLD"}
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    from tradingagents.storage import sqlite_history
    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert len(rows) == 1  # UPSERT, not duplicate
