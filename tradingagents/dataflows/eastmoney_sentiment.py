"""Eastmoney 千股千评 quantified sentiment fetcher (A-share only).

This module aggregates Eastmoney's "千股千评" structured sentiment data
via the akshare library. It serves as the A-share analog of StockTwits:
both produce quantified, ticker-indexed sentiment signals — StockTwits
exposes Bullish/Bearish message ratios, while Eastmoney exposes:

  * 综合得分 (composite score, 0–100)
  * 关注指数 (attention index, last 30 days)
  * 机构参与度 (institutional participation %)
  * 主力成本 (main-capital cost basis, RMB)
  * 5 日参与意愿变化（recent sentiment momentum）

These metrics carry richer signal than StockTwits' raw multi-source
aggregation and are unique to the A-share market, so they replace
StockTwits cleanly for Chinese tickers.

All functions degrade gracefully and return a formatted plaintext block
ready for prompt injection.
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

# Silence pandas warnings raised by some akshare endpoints.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


def to_a_share_code(ticker: str) -> Optional[str]:
    """Convert internal ticker formats to akshare's bare 6-digit A-share code.

    Returns ``None`` if the ticker is not an A-share symbol (US/HK/etc.).

    Examples
    --------
    >>> to_a_share_code("300990.SZ")  -> "300990"
    >>> to_a_share_code("600036.SS")  -> "600036"
    >>> to_a_share_code("SH.600036")  -> "600036"
    >>> to_a_share_code("AAPL")       -> None
    """
    s = (ticker or "").strip().upper()
    m = re.match(r"^(\d{6})(\.(SS|SZ))?$", s)
    if m:
        return m.group(1)
    m = re.match(r"^(SH|SZ)\.?(\d{6})$", s)
    if m:
        return m.group(2)
    return None


def _safe_value(row, key: str) -> str:
    """Read a column from a pandas Series with safe fallback to '—'."""
    try:
        v = row.get(key)
        if v is None or (hasattr(v, "isna") and v.isna()):
            return "—"
        return str(v)
    except Exception:
        return "—"


def fetch_eastmoney_sentiment(ticker: str) -> str:
    """Aggregate Eastmoney 千股千评 metrics into a plaintext block.

    Returns a clear placeholder string for non-A-share tickers, when
    akshare is unavailable, or when the upstream call fails.
    """
    code = to_a_share_code(ticker)
    if code is None:
        return (
            f"<东方财富千股千评仅覆盖 A 股，无 {ticker.upper()} 数据。"
            f"对应美股 / 港股请参考 StockTwits 或其他源。>"
        )

    try:
        import akshare as ak
    except ImportError:
        return (
            "<东方财富情绪数据源不可用：未安装 akshare。"
            "请运行 `pip install akshare`。>"
        )

    # ---- 1) Today's composite snapshot (千股千评 overview) ----
    snapshot_line = ""
    try:
        overview = ak.stock_comment_em()
        row = overview[overview["代码"] == code]
        if len(row) > 0:
            r = row.iloc[0]
            snapshot_line = (
                f"今日快照 · "
                f"综合得分 {_safe_value(r, '综合得分')} / 100 · "
                f"关注指数 {_safe_value(r, '关注指数')} · "
                f"机构参与度 {_safe_value(r, '机构参与度')}% · "
                f"主力成本 {_safe_value(r, '主力成本')} 元 · "
                f"市盈率 {_safe_value(r, '市盈率')} · "
                f"换手率 {_safe_value(r, '换手率')}% · "
                f"目前排名 {_safe_value(r, '目前排名')}"
            )
    except Exception as exc:
        logger.debug("stock_comment_em failed for %s: %s", code, exc)

    # ---- 2) Attention-index trend (30-day history) ----
    attention_line = ""
    try:
        focus = ak.stock_comment_detail_scrd_focus_em(symbol=code)
        if len(focus) >= 2:
            latest = float(focus["用户关注指数"].iloc[-1])
            earliest = float(focus["用户关注指数"].iloc[0])
            delta = latest - earliest
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            attention_line = (
                f"关注度 30 天趋势 · "
                f"{focus['交易日'].iloc[0]} 起 {earliest:.1f} {arrow} "
                f"{focus['交易日'].iloc[-1]} 终值 {latest:.1f}（变化 {delta:+.1f}）"
            )
    except Exception as exc:
        logger.debug("stock_comment_detail_scrd_focus_em failed for %s: %s", code, exc)

    # ---- 3) 5-day participation-willingness momentum ----
    desire_line = ""
    try:
        desire = ak.stock_comment_detail_scrd_desire_daily_em(symbol=code)
        if len(desire) > 0:
            latest = desire.iloc[-1]
            desire_line = (
                f"近 5 日参与意愿 · "
                f"最新交易日 {_safe_value(latest, '交易日')} · "
                f"当日意愿变化 {_safe_value(latest, '当日意愿上升')} · "
                f"5 日均变化 {_safe_value(latest, '5日平均参与意愿变化')}"
            )
    except Exception as exc:
        logger.debug("stock_comment_detail_scrd_desire_daily_em failed for %s: %s", code, exc)

    # ---- 4) Composite-rating recent history ----
    rating_line = ""
    try:
        ratings = ak.stock_comment_detail_zhpj_lspf_em(symbol=code)
        if len(ratings) >= 5:
            recent = ratings.tail(5)
            seq = " → ".join(
                f"{row['交易日']}: {float(row['评分']):.1f}"
                for _, row in recent.iterrows()
            )
            rating_line = f"综合评分近 5 日 · {seq}"
    except Exception as exc:
        logger.debug("stock_comment_detail_zhpj_lspf_em failed for %s: %s", code, exc)

    blocks = [
        f"东方财富千股千评（{code}） — A 股结构化情绪指标",
    ]
    if snapshot_line:
        blocks.append("• " + snapshot_line)
    if attention_line:
        blocks.append("• " + attention_line)
    if desire_line:
        blocks.append("• " + desire_line)
    if rating_line:
        blocks.append("• " + rating_line)

    if len(blocks) == 1:
        return f"<未在东方财富千股千评数据中找到 {code} 的指标。>"

    blocks.append(
        "注：综合得分 ≥70 偏强 / 50–70 中性偏强 / 30–50 中性偏弱 / <30 偏弱；"
        "关注指数反映散户关注度（0–100）；机构参与度越高表明主力资金活跃。"
    )
    return "\n".join(blocks)
