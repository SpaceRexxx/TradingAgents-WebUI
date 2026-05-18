import json
from pathlib import Path

from backend.services.persistence import persist_run


def test_persist_run_writes_json_pdf_and_indexes(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 fake report")
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
    pdf_file = tmp_path / "TEST" / "2026-01-01" / "report.pdf"
    assert json_file.exists()
    assert pdf_file.exists()
    assert pdf_file.read_bytes().startswith(b"%PDF")
    saved = json.loads(json_file.read_text())
    assert "messages" not in saved
    assert saved["final_trade_decision"] == "BUY: strong"

    from tradingagents.storage import sqlite_history

    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert rows and rows[0]["ticker"] == "TEST"
    assert rows[0]["json_path"] == str(json_file)
    assert rows[0]["pdf_path"] == str(pdf_file)


def test_persist_run_is_idempotent(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 fake report")
    fs = {"company_of_interest": "TEST", "trade_date": "2026-01-01",
          "final_trade_decision": "HOLD"}
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    persist_run(results_dir=tmp_path, ticker="TEST", trade_date="2026-01-01",
                final_state=fs, model="m", provider="p")
    from tradingagents.storage import sqlite_history
    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert len(rows) == 1  # UPSERT, not duplicate


def test_persist_run_keeps_json_when_pdf_generation_fails(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service
    from tradingagents.storage import sqlite_history

    def fail(_html: str) -> bytes:
        raise RuntimeError("playwright unavailable")

    monkeypatch.setattr(pdf_service, "_render_pdf", fail)
    fs = {
        "company_of_interest": "TEST",
        "trade_date": "2026-01-01",
        "final_trade_decision": "HOLD",
    }

    persist_run(
        results_dir=tmp_path,
        ticker="TEST",
        trade_date="2026-01-01",
        final_state=fs,
        model="m",
        provider="p",
    )

    json_file = tmp_path / "TEST" / "2026-01-01" / "final_state_report.json"
    pdf_file = tmp_path / "TEST" / "2026-01-01" / "report.pdf"
    assert json_file.exists()
    assert not pdf_file.exists()

    rows = sqlite_history.query_analyses(tmp_path, ticker="TEST")
    assert rows[0]["json_path"] == str(json_file)
    assert rows[0]["pdf_path"] is None
