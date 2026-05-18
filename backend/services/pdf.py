from __future__ import annotations

import html
import subprocess
import sys

import markdown2

_SECTIONS = [
    ("第一阶段：分析师团队报告", [
        ("market_report", "市场分析报告"),
        ("sentiment_report", "社交情绪报告"),
        ("news_report", "新闻分析报告"),
        ("fundamentals_report", "基本面分析报告"),
    ]),
    ("第二阶段：研究团队辩论", [
        ("investment_debate_state.bull_history", "多头研究员辩论"),
        ("investment_debate_state.bear_history", "空头研究员辩论"),
        ("investment_plan", "研究经理总结"),
    ]),
    ("第三阶段：交易团队计划", [("trader_investment_plan", "")]),
    ("第四/五阶段：风险管理与最终决策", [
        ("risk_debate_state.aggressive_history", "激进型分析师辩论"),
        ("risk_debate_state.conservative_history", "保守型分析师辩论"),
        ("risk_debate_state.neutral_history", "中立型分析师辩论"),
    ]),
]

_CSS = (
    "body { font-family: sans-serif; font-size: 10pt; line-height: 1.6; } "
    "h1 { font-size: 22pt; color: #1E293B; text-align: center; } "
    "h2 { font-size: 16pt; color: #334155; border-bottom: 2px solid #f1f5f9; "
    "padding-bottom: 6px; margin-top: 25px;} "
    "h3 { font-size: 13pt; color: #475569; margin-top: 20px;} "
    "table { border-collapse: collapse; width: 100%; margin-top: 15px; } "
    "th, td { border: 1px solid #e2e8f0; text-align: left; padding: 8px; } "
    "th { background-color: #f8fafc; font-weight: bold; } "
    ".decision-table td:first-child { background:#f8fafc; font-weight:bold; width:30%; } "
    ".report-footer { margin-top:30px; padding-top:10px; border-top:1px solid #e2e8f0; font-size:8pt; color:#94a3b8; }"
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


_DECISION_ROWS = [
    ("rating", "评级"),
    ("conviction_score", "信心度"),
    ("price_target", "目标位"),
    ("stop_loss", "止损位"),
    ("breakout_point", "突破位"),
    ("time_horizon", "时间窗口"),
    ("outlook_30d", "30天展望"),
    ("outlook_60d", "60天展望"),
    ("outlook_90d", "90天展望"),
]


def _decision_table_html(decision: dict) -> str:
    rows = []
    for key, label in _DECISION_ROWS:
        val = decision.get(key)
        if val is None or val == "":
            continue
        cell = f"{val}/10" if key == "conviction_score" else val
        rows.append(
            f"<tr><td>{html.escape(label)}</td>"
            f"<td>{html.escape(str(cell))}</td></tr>"
        )
    table = f"<table class='decision-table'>{''.join(rows)}</table>" if rows else ""
    summary = decision.get("executive_summary") or ""
    thesis = decision.get("investment_thesis") or ""
    blocks = [table]
    if summary:
        blocks.append(
            f"<h3>核心决策摘要</h3>"
            f"{markdown2.markdown(str(summary), extras=['tables', 'fenced-code-blocks', 'header-ids'])}"
        )
    if thesis:
        blocks.append(
            f"<h3>投资论据</h3>"
            f"{markdown2.markdown(str(thesis), extras=['tables', 'fenced-code-blocks', 'header-ids'])}"
        )
    return "\n".join(b for b in blocks if b)


def _footer_html(final_state: dict) -> str:
    meta = final_state.get("run_meta")
    if not isinstance(meta, dict):
        return ""
    tokens = meta.get("tokens") or {}
    line = (
        f"生成时间: {html.escape(str(meta.get('generated_at') or '-'))} | "
        f"模型: {html.escape(str(meta.get('model') or '-'))} | "
        f"供应商: {html.escape(str(meta.get('provider') or '-'))} | "
        f"Tokens: {html.escape(str(tokens.get('total_tokens') or '-'))} | "
        f"成本(USD): {html.escape(str(tokens.get('cost_usd') or '-'))}"
    )
    disclaimer = html.escape(str(meta.get("disclaimer") or ""))
    return f"<div class='report-footer'><p>{line}</p><p>{disclaimer}</p></div>"


def _build_html(final_state: dict, ticker: str, trade_date: str) -> str:
    safe_ticker = html.escape(ticker)
    safe_date = html.escape(trade_date)
    parts = [f"<h1>{safe_ticker} 交易分析报告</h1>",
             f"<p><b>分析日期:</b> {safe_date}</p><hr>"]
    for section_title, keys in _SECTIONS:
        chunk = []
        for key, sub_title in keys:
            val = _get_section(final_state, key)
            if val:
                html_md = markdown2.markdown(
                    val, extras=["tables", "fenced-code-blocks", "header-ids"]
                )
                chunk.append(f"<h3>{sub_title}</h3>{html_md}" if sub_title else html_md)
        if chunk:
            parts.append(f"<h2>{section_title}</h2>" + "\n".join(chunk))
    decision = final_state.get("portfolio_decision")
    if isinstance(decision, dict):
        parts.append("<h2>最终投资决策</h2>" + _decision_table_html(decision))
    elif final_state.get("final_trade_decision"):
        parts.append(
            "<h2>最终投资决策</h2>"
            + markdown2.markdown(
                str(final_state["final_trade_decision"]),
                extras=["tables", "fenced-code-blocks", "header-ids"],
            )
        )
    body = "\n".join(parts) + _footer_html(final_state)
    return f"<html><head><meta charset='UTF-8'><style>{_CSS}</style></head><body>{body}</body></html>"


def _get_section(final_state: dict, key: str) -> str:
    value: object = final_state
    for part in key.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")
    return value if isinstance(value, str) else ""


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
