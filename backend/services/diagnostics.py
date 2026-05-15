from __future__ import annotations

import shutil


def detect_degraded_sources() -> list[str]:
    """Lightweight probe: which data sources are unavailable. Ported from
    webapp.py:_detect_degraded_sources (kept independent of Streamlit)."""
    degraded: list[str] = []
    if not shutil.which("opencli"):
        degraded.append("OpenCLI 未安装 → 雪球 / Reddit / 新浪 数据源不可用")
    try:
        import akshare  # noqa: F401
    except ImportError:
        degraded.append("akshare 未安装 → A 股数据源不可用（千股千评 / 公告 / 财联社）")
    return degraded
