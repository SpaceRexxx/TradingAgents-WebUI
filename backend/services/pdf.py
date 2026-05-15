from __future__ import annotations

import html
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
    safe_ticker = html.escape(ticker)
    safe_date = html.escape(trade_date)
    parts = [f"<h1>{safe_ticker} 交易分析报告</h1>",
             f"<p><b>分析日期:</b> {safe_date}</p><hr>"]
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
