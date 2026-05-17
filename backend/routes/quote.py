from __future__ import annotations

import json
import subprocess
import time

from fastapi import APIRouter, Response

from tradingagents.dataflows.xueqiu import _opencli_available, to_xueqiu_symbol

router = APIRouter(prefix="/api", tags=["quote"])

_CACHE_TTL = 60.0
_TIMEOUT = 8.0
_cache: dict[str, tuple[float, dict | None]] = {}


def _live_quote(symbol: str) -> dict | None:
    """Run `opencli xueqiu stock {symbol} -f json`; None on any failure.

    Mirrors the retired Streamlit logic (webapp.py:1230-1250) so the data
    source and degradation behavior stay identical.
    """
    if not _opencli_available():
        return None
    try:
        proc = subprocess.run(
            ["opencli", "xueqiu", "stock", symbol, "-f", "json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return None
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None
    return {
        "name": data.get("name", ""),
        "price": data.get("price"),
        "change": data.get("change"),
        "changePercent": data.get("changePercent"),
    }


@router.get("/quote/{ticker}")
def quote(ticker: str, response: Response):
    """Live price + Chinese name for a ticker, or 204 when unavailable."""
    try:
        symbol = to_xueqiu_symbol(ticker) or ticker
    except Exception:
        symbol = ticker

    now = time.monotonic()
    hit = _cache.get(symbol)
    if hit is not None and now - hit[0] < _CACHE_TTL:
        result = hit[1]
    else:
        result = _live_quote(symbol)
        _cache[symbol] = (now, result)

    if result is None:
        return Response(status_code=204)
    return result
