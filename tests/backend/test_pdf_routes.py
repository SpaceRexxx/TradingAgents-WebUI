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


def test_report_known_run_returns_final_state(seeded):
    with _client() as client:
        resp = client.get("/api/runs/TEST/2026-01-01/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "TEST"
        assert body["trade_date"] == "2026-01-01"
        assert body["final_state"]["market_report"] == "# Market\nstrong"


def test_report_unknown_run_returns_404(seeded):
    with _client() as client:
        resp = client.get("/api/runs/GHOST/2099-01-01/report")
        assert resp.status_code == 404


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


def test_pdf_html_renders_decision_table_and_footer():
    from backend.services.pdf import _build_html

    final_state = {
        "market_report": "# M\nx",
        "final_trade_decision": "**Rating**: Buy",
        "portfolio_decision": {
            "rating": "Buy",
            "conviction_score": 8,
            "executive_summary": "建仓区间 250-255",
            "investment_thesis": "多头论据更强",
            "price_target": 300.0,
            "stop_loss": 240.0,
            "breakout_point": 260.0,
            "time_horizon": "1-3 个月",
            "outlook_30d": "区间震荡",
            "outlook_60d": "趋势向上",
            "outlook_90d": "突破确认加仓",
        },
        "run_meta": {
            "generated_at": "2026-02-02T03:04:05Z",
            "model": "deepseek-v4-pro",
            "provider": "DeepSeek",
            "tokens": {"total_tokens": 1234, "cost_usd": 0.05},
            "disclaimer": "本报告由 AI 多智能体系统自动生成,不构成任何投资建议。",
        },
    }
    html = _build_html(final_state, "TEST", "2026-02-02")
    assert "<table" in html
    assert "8/10" in html
    assert "建仓区间 250-255" in html
    assert "240.0" in html
    assert "本报告由 AI 多智能体系统自动生成" in html
    assert "deepseek-v4-pro" in html


def test_pdf_html_falls_back_to_markdown_when_no_structured_decision():
    from backend.services.pdf import _build_html

    html = _build_html(
        {"final_trade_decision": "**Rating**: Hold\n纯文本回退"},
        "TEST",
        "2026-02-02",
    )
    assert "纯文本回退" in html
