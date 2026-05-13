"""Sina Finance 7×24 macro news fetcher via OpenCLI.

Sina Finance's 7×24 live news stream is the gold-standard source for
Chinese macro / policy / market-moving headlines:

  * Real-time (minute-level latency)
  * Covers both A-share and global markets
  * Each item carries a view-count signal (popular items = strong attention)
  * Pure Chinese, ready for direct LLM consumption

Used as the macro-news source for A-share analysis, replacing Yahoo
Finance's English macro queries which have poor China-relevant coverage.

Uses OpenCLI's ``sinafinance`` adapter. The ``news`` subcommand is a
public endpoint (no login required), so this works even when the user
isn't logged into Sina.

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

_OPENCLI_BIN = "opencli"
_DEFAULT_TIMEOUT = 30.0


def _opencli_available() -> bool:
    return shutil.which(_OPENCLI_BIN) is not None


def fetch_sina_macro_news(
    limit: int = 30,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str:
    """Fetch Sina Finance 7×24 macro news and return as a formatted block.

    No date-range filter — Sina returns the latest ``limit`` items in
    reverse-chronological order. Each item includes a view-count signal,
    useful for the LLM to weight items by attention.
    """
    if not _opencli_available():
        return (
            "<新浪财经数据源不可用：opencli 命令未安装。"
            "请运行 `npm install -g @jackwener/opencli`。>"
        )

    cmd = [
        _OPENCLI_BIN, "sinafinance", "news",
        "--limit", str(limit),
        "-f", "json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.debug("OpenCLI sinafinance news timed out")
        return "<新浪财经数据源：请求超时。>"
    except FileNotFoundError:
        return "<新浪财经数据源不可用：opencli 命令未找到。>"

    if proc.returncode != 0:
        logger.debug(
            "OpenCLI sinafinance news failed (rc=%d): %s",
            proc.returncode, (proc.stderr or "").strip()[:300],
        )
        return "<新浪财经数据源：拉取失败。>"

    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        logger.debug("OpenCLI sinafinance news returned non-JSON: %s", exc)
        return "<新浪财经数据源：返回数据格式异常。>"

    if not isinstance(data, list) or not data:
        return "<新浪财经数据源：未返回任何新闻。>"

    lines = [
        f"新浪财经 7×24 实时快讯（最新 {len(data)} 条）：",
        "",
    ]
    for item in data:
        time_str = (item.get("time") or "").strip()
        # Sina returns 'YYYY-MM-DD HH:MM:SS'; trim to 'MM-DD HH:MM' for compact display
        if len(time_str) >= 16:
            time_str = time_str[5:16]
        content = (item.get("content") or "").replace("\n", " ").strip()
        if len(content) > 320:
            content = content[:320] + "…"
        views = (item.get("views") or "").strip()
        view_part = f" · {views}" if views else ""
        lines.append(f"[{time_str}{view_part}] {content}")

    return "\n".join(lines)
