"""Xueqiu (雪球) discussion fetcher via OpenCLI.

Xueqiu is China's largest serious-investor stock discussion platform.
Compared to Eastmoney 股吧 (which is more retail-noisy, like r/wallstreetbets),
Xueqiu posts come from a higher-signal user base (analysts, fund managers,
long-term investors), making it the closest A-share analog to Reddit's
r/investing + r/stocks community.

Uses OpenCLI (https://github.com/jackwener/OpenCLI) to drive the user's
logged-in Chrome session, since Xueqiu does not expose a public REST API
for discussion streams and its scraping endpoints are heavily protected.

Prerequisites (one-time setup):
  1. Install OpenCLI:                npm install -g @jackwener/opencli
  2. Install OpenCLI Chrome extension
  3. Log into xueqiu.com in that Chrome profile
  4. Verify:                         opencli doctor

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_OPENCLI_BIN = "opencli"
_DEFAULT_TIMEOUT = 30.0


def _opencli_available() -> bool:
    """Return True iff the ``opencli`` binary is on PATH."""
    return shutil.which(_OPENCLI_BIN) is not None


def to_xueqiu_symbol(ticker: str) -> Optional[str]:
    """Convert internal ticker formats to Xueqiu's symbol convention.

    Examples
    --------
    >>> to_xueqiu_symbol("300990.SZ")  -> "SZ300990"
    >>> to_xueqiu_symbol("600036.SS")  -> "SH600036"
    >>> to_xueqiu_symbol("SH.600036")  -> "SH600036"
    >>> to_xueqiu_symbol("AAPL")       -> "AAPL"
    >>> to_xueqiu_symbol("0700.HK")    -> "00700"
    """
    s = (ticker or "").strip().upper()

    # 600036.SS / 000001.SZ  -> SH600036 / SZ000001
    m = re.match(r"^(\d+)\.(SS|SZ)$", s)
    if m:
        code, ex = m.groups()
        return ("SH" if ex == "SS" else "SZ") + code

    # SH.600036 / SZ.000001  -> SH600036 / SZ000001
    m = re.match(r"^(SH|SZ)\.(\d+)$", s)
    if m:
        return m.group(1) + m.group(2)

    # SH600036 / SZ000001 — already xueqiu form
    m = re.match(r"^(SH|SZ)\d+$", s)
    if m:
        return s

    # Bare 6-digit Chinese A-share code -> infer exchange
    m = re.match(r"^\d{6}$", s)
    if m:
        prefix = "SH" if s.startswith(("60", "68")) else "SZ"
        return prefix + s

    # HK tickers: 0700.HK / 700.HK -> 00700 (Xueqiu uses 5-digit zero-padded)
    m = re.match(r"^(\d+)\.HK$", s)
    if m:
        return m.group(1).zfill(5)

    # US tickers (AAPL, TSLA, etc.) — Xueqiu uses bare uppercase symbol
    if re.match(r"^[A-Z]{1,5}$", s):
        return s

    # Anything else: return as-is and let Xueqiu try.
    return s


def fetch_xueqiu_comments(
    ticker: str,
    limit: int = 15,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str:
    """Fetch recent Xueqiu discussion posts for ``ticker`` and return them
    as a formatted plaintext block.

    Returns a placeholder string when OpenCLI is unavailable, the symbol
    has no discussion, or the call fails — the caller never has to
    special-case None or exceptions.
    """
    if not _opencli_available():
        return (
            "<雪球数据源不可用：opencli 命令未安装。"
            "请运行 `npm install -g @jackwener/opencli` 并装好 Browser Bridge 扩展。>"
        )

    symbol = to_xueqiu_symbol(ticker)
    if not symbol:
        return f"<雪球数据源：无法将 {ticker} 转换为雪球代码格式。>"

    cmd = [
        _OPENCLI_BIN, "xueqiu", "comments", symbol,
        "--limit", str(limit),
        "-f", "json",
        "--window", "background",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.debug("OpenCLI xueqiu timed out for %s", symbol)
        return f"<雪球数据源：请求 {symbol} 超时。>"
    except FileNotFoundError:
        return "<雪球数据源不可用：opencli 命令未找到。>"

    if proc.returncode != 0:
        logger.debug(
            "OpenCLI xueqiu failed for %s (rc=%d): %s",
            symbol, proc.returncode, (proc.stderr or "").strip()[:300],
        )
        return f"<雪球数据源：拉取 {symbol} 失败（可能 Chrome 未运行或未登录雪球）。>"

    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        logger.debug("OpenCLI xueqiu returned non-JSON for %s: %s", symbol, exc)
        return f"<雪球数据源：返回数据格式异常 ({symbol})。>"

    if not isinstance(data, list) or not data:
        return f"<未在雪球上找到 {symbol} 的近期讨论。>"

    total_likes = sum(int(p.get("likes") or 0) for p in data)
    total_replies = sum(int(p.get("replies") or 0) for p in data)
    total_retweets = sum(int(p.get("retweets") or 0) for p in data)
    summary = (
        f"雪球（{symbol}）最近 {len(data)} 条讨论 · "
        f"总互动：{total_likes} 赞 · {total_replies} 评论 · {total_retweets} 转发"
    )

    lines = [summary, ""]
    for p in data:
        author = (p.get("author") or "?").strip()
        text = (p.get("text") or "").replace("\n", " ").strip()
        if len(text) > 280:
            text = text[:280] + "…"
        likes = int(p.get("likes") or 0)
        replies = int(p.get("replies") or 0)
        retweets = int(p.get("retweets") or 0)
        created = (p.get("created_at") or "")[:10]  # YYYY-MM-DD
        lines.append(
            f"[{created} · @{author} · {likes}赞/{replies}评/{retweets}转] {text}"
        )

    return "\n".join(lines)
