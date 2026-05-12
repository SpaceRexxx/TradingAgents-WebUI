"""A-share ticker-specific news fetcher.

Combines two complementary sources for Chinese stock news:

  1. **Eastmoney corporate announcements** (via akshare ``stock_notice_report``)
     — official corporate disclosures filed with the exchange. The most
     authoritative news source for A-shares: earnings reports, M&A,
     major contracts, shareholder changes, share-buyback plans, etc.
     Iterates over the past N trading days to find ticker-specific items.

  2. **Cailianpress global news** (via akshare ``stock_info_global_cls``)
     — fast-moving financial newswire, filtered by Chinese company name.
     Captures market-moving headlines that haven't yet shown up as
     formal announcements.

Returns a unified plaintext block ready for prompt injection. Each source
is best-effort: if either fails the function still returns whatever the
other yielded.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_OPENCLI_BIN = "opencli"
_DEFAULT_TIMEOUT = 30.0
_CACHE_TTL_SECONDS = 6 * 3600   # 6 hours — announcements rarely intra-day
_CACHE_DIR = Path.home() / ".tradingagents" / "cache" / "a_share_notices"


def _opencli_available() -> bool:
    return shutil.which(_OPENCLI_BIN) is not None


@contextmanager
def _without_proxy():
    """Temporarily remove HTTP proxy env vars (akshare uses requests which
    honors them; Eastmoney endpoints are inside China and reject most VPN
    exit IPs, so the proxy must be bypassed)."""
    saved = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


def _load_notices_for_date(date_str: str):
    """Return cached DataFrame of all A-share notices for ``date_str`` (YYYYMMDD),
    or fetch from akshare and cache.

    Cache lives under ``~/.tradingagents/cache/a_share_notices/{date}.pkl`` and
    is reused across all tickers + analyst runs within ``_CACHE_TTL_SECONDS``.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{date_str}.pkl"

    # Cache freshness check
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            try:
                with cache_path.open("rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        import akshare as ak
    except ImportError:
        return None
    try:
        with _without_proxy():
            df = ak.stock_notice_report(symbol="全部", date=date_str)
    except Exception as exc:
        logger.debug("stock_notice_report(%s) failed: %s", date_str, exc)
        return None
    if df is None or len(df) == 0:
        return df  # cache the empty result too

    try:
        with cache_path.open("wb") as f:
            pickle.dump(df, f)
    except Exception as exc:
        logger.debug("Notice cache write failed: %s", exc)
    return df


def _fetch_eastmoney_announcements(code: str, lookback_days: int = 5) -> list[dict]:
    """Pull recent A-share corporate announcements for ``code``.

    Uses akshare ``stock_notice_report`` which returns the full-market
    announcement list for a given date (~1000-2000 items). We iterate
    backwards ``lookback_days`` calendar days and filter client-side by
    code. Each call costs ~3-5s, so 7-day lookback ≈ 25-35s; cached
    aggressively to amortise across analyst runs.
    """
    from datetime import datetime, timedelta

    results: list[dict] = []
    today = datetime.now()
    for delta in range(lookback_days + 1):
        date = today - timedelta(days=delta)
        date_str = date.strftime("%Y%m%d")
        df = _load_notices_for_date(date_str)
        if df is None or len(df) == 0:
            continue
        try:
            match = df[df["代码"] == code]
        except Exception:
            continue
        for _, row in match.iterrows():
            results.append({
                "date": str(row.get("公告日期", "")).strip(),
                "title": str(row.get("公告标题", "")).strip(),
                "category": str(row.get("公告类型", "")).strip(),
                "url": str(row.get("网址", "")).strip(),
            })
        if len(results) >= 25:
            break

    # Sort newest first
    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results


def _fetch_cls_news(company_name: str) -> list[dict]:
    """Pull Cailianpress global news and filter by ``company_name`` substring."""
    try:
        import akshare as ak
    except ImportError:
        return []
    try:
        with _without_proxy():
            df = ak.stock_info_global_cls()
    except Exception as exc:
        logger.debug("stock_info_global_cls failed: %s", exc)
        return []

    if df is None or len(df) == 0:
        return []
    try:
        mask = (
            df["标题"].astype(str).str.contains(company_name, na=False) |
            df["内容"].astype(str).str.contains(company_name, na=False)
        )
        filtered = df[mask]
    except Exception:
        return []

    out: list[dict] = []
    for _, row in filtered.iterrows():
        out.append({
            "title": str(row.get("标题", "")).strip(),
            "content": str(row.get("内容", "")).strip(),
            "date": str(row.get("发布日期", "")).strip(),
            "time": str(row.get("发布时间", "")).strip(),
        })
    return out


def _resolve_company_name(code: str) -> Optional[str]:
    """Look up the Chinese company name for an A-share code via OpenCLI xueqiu."""
    if not _opencli_available():
        return None
    # 600036 -> SH600036, 300990 -> SZ300990
    prefix = "SH" if code.startswith(("60", "68")) else "SZ"
    symbol = prefix + code
    try:
        proc = subprocess.run(
            [_OPENCLI_BIN, "xueqiu", "stock", symbol, "-f", "json", "--window", "background"],
            capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if isinstance(data, list) and data:
        return (data[0] or {}).get("name")
    if isinstance(data, dict):
        return data.get("name")
    return None


def fetch_a_share_news(code: str, max_items: int = 25) -> str:
    """Aggregate A-share ticker-specific news from announcements + Cailianpress.

    ``code`` is a bare 6-digit A-share code (e.g. ``"300990"``).
    """
    if not code or not code.isdigit() or len(code) != 6:
        return f"<A 股新闻数据源：非法的代码 {code!r}。>"

    company_name = _resolve_company_name(code)

    announcements = _fetch_eastmoney_announcements(code)
    cls_items = _fetch_cls_news(company_name) if company_name else []

    blocks: list[str] = []
    blocks.append(
        f"A 股个股新闻聚合（{code}{'·' + company_name if company_name else ''}）"
    )

    if announcements:
        blocks.append(f"\n## 上市公司公告（东方财富，最近 7 天，共 {len(announcements)} 条）")
        for a in announcements[:max_items]:
            t = (a.get("date") or "").strip()[:10]
            title = (a.get("title") or "").strip()
            category = (a.get("category") or "").strip()
            cat_part = f"【{category}】" if category else ""
            blocks.append(f"  [{t}] {cat_part}{title}")
    else:
        blocks.append("\n## 上市公司公告：近 7 天无新公告或上游数据源不可用。")

    if cls_items:
        blocks.append(
            f"\n## 财联社新闻按公司名匹配（{company_name}，{len(cls_items)} 条）"
        )
        for n in cls_items[:max_items]:
            t = (n.get("date") or "") + " " + (n.get("time") or "")[:5]
            title = (n.get("title") or "").strip()
            content = (n.get("content") or "").strip()
            if len(content) > 240:
                content = content[:240] + "…"
            blocks.append(f"  [{t.strip()}] {title}\n    {content}")
    elif company_name:
        blocks.append(
            f"\n## 财联社新闻：近期未发现含 '{company_name}' 的快讯。"
        )

    if not announcements and not cls_items:
        blocks.append(
            "\n注：当前数据源未返回该标的的新闻或公告；可能近期无重大公司事件，"
            "或上游数据源临时不可用。请结合宏观新闻和舆情数据综合判断。"
        )

    return "\n".join(blocks)
