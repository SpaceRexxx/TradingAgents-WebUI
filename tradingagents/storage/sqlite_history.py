"""SQLite index for historical analyses.

Replaces the previous brittle approach of ``rglob`` over the JSON tree.
The on-disk layout (``results_dir/{ticker}/{date}/final_state_report.json``)
is unchanged — SQLite is purely an index for fast filtered queries:

  * "All Buy ratings since 2026-01-01"
  * "Last 5 analyses of NVDA"
  * "Aggregated rating counts by ticker"

Schema
------
``analyses(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    trade_date    TEXT    NOT NULL,
    rating        TEXT,           -- Buy / Overweight / Hold / Underweight / Sell
    summary       TEXT,           -- executive summary truncated to 500 chars
    model         TEXT,           -- model id used for the deep_think_llm
    provider      TEXT,           -- e.g. DeepSeek / OpenAI
    has_position  TEXT,           -- 已持有 / 未持有
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    json_path     TEXT    NOT NULL,
    pdf_path      TEXT,
    UNIQUE(ticker, trade_date)
)``

On startup, the index auto-rebuilds from any json files newer than the
last index timestamp, so the index always reflects what's on disk even
if some other tool wrote a new report directly.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional


_DB_FILENAME = "history.sqlite"


def _db_path(results_dir: Path) -> Path:
    return Path(results_dir) / _DB_FILENAME


@contextmanager
def _connect(results_dir: Path):
    """Yield an sqlite connection rooted at ``results_dir/history.sqlite``."""
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path(results_dir)))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            trade_date   TEXT NOT NULL,
            rating       TEXT,
            summary      TEXT,
            model        TEXT,
            provider     TEXT,
            has_position TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            json_path    TEXT NOT NULL,
            pdf_path     TEXT,
            note         TEXT,           -- Stage 8: 用户备注
            UNIQUE(ticker, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_analyses_ticker     ON analyses(ticker);
        CREATE INDEX IF NOT EXISTS idx_analyses_trade_date ON analyses(trade_date);
        CREATE INDEX IF NOT EXISTS idx_analyses_rating     ON analyses(rating);
        """
    )
    # 兼容旧表：如缺少 note 列就补
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(analyses)")}
        if "note" not in cols:
            conn.execute("ALTER TABLE analyses ADD COLUMN note TEXT")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# 同时匹配英文 "**Rating**: Buy" 和中文 "**评级**：Hold（持有）" 等格式。
# 英文评级关键词放第一组，捕获即可。
_RATING_RE = re.compile(
    r"\*\*?(?:Rating|评级|核心评级|总体建议)\*?\*?\s*[:：]\s*\*?\*?"
    r"(Buy|Overweight|Hold|Underweight|Sell)",
    re.IGNORECASE,
)


def _extract_rating(decision_text: str) -> Optional[str]:
    """Pull the Buy/Overweight/Hold/Underweight/Sell rating out of the
    final-decision markdown produced by the Portfolio Manager."""
    if not decision_text:
        return None
    m = _RATING_RE.search(decision_text)
    if m:
        return m.group(1).capitalize()
    return None


def _extract_summary(decision_text: str, max_len: int = 500) -> Optional[str]:
    """Pull the executive summary section out of the PM markdown."""
    if not decision_text:
        return None
    # Look for "**Executive Summary**:" or 行政摘要
    m = re.search(
        r"\*\*?(?:Executive Summary|行政摘要|核心决策摘要)\*?\*?\s*[:：]\s*(.+?)(?=\n\n\*\*|\Z)",
        decision_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        text = m.group(1).strip().replace("\n", " ")
        return text[:max_len]
    # Fallback: first 500 chars of the decision text
    return decision_text.strip()[:max_len]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def index_one_analysis(
    results_dir: Path | str,
    *,
    ticker: str,
    trade_date: str,
    json_path: Path | str,
    pdf_path: Optional[Path | str] = None,
    decision_text: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    has_position: Optional[str] = None,
) -> None:
    """Insert or update one analysis row. Idempotent (UPSERT)."""
    results_dir = Path(results_dir)
    rating = _extract_rating(decision_text or "")
    summary = _extract_summary(decision_text or "")
    with _connect(results_dir) as conn:
        _init_schema(conn)
        conn.execute(
            """
            INSERT INTO analyses (
                ticker, trade_date, rating, summary, model, provider,
                has_position, json_path, pdf_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, trade_date) DO UPDATE SET
                rating       = excluded.rating,
                summary      = excluded.summary,
                model        = excluded.model,
                provider     = excluded.provider,
                has_position = excluded.has_position,
                json_path    = excluded.json_path,
                pdf_path     = excluded.pdf_path,
                created_at   = datetime('now')
            """,
            (
                ticker, trade_date, rating, summary, model, provider,
                has_position, str(json_path),
                str(pdf_path) if pdf_path else None,
            ),
        )


def rebuild_from_disk(results_dir: Path | str) -> int:
    """Walk the results tree and insert any analyses that aren't yet in the index.

    Returns the number of NEW rows inserted (existing rows are left alone).
    """
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return 0

    with _connect(results_dir) as conn:
        _init_schema(conn)
        existing = {
            (row["ticker"], row["trade_date"])
            for row in conn.execute("SELECT ticker, trade_date FROM analyses")
        }

    new_count = 0
    for json_path in results_dir.rglob("final_state_report.json"):
        try:
            date = json_path.parent.name
            ticker = json_path.parent.parent.name
            if (ticker, date) in existing:
                continue
            pdf_path = json_path.parent / "report.pdf"
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            decision_text = data.get("final_trade_decision", "")
            index_one_analysis(
                results_dir,
                ticker=ticker,
                trade_date=date,
                json_path=json_path,
                pdf_path=pdf_path if pdf_path.exists() else None,
                decision_text=decision_text,
            )
            new_count += 1
        except Exception:
            continue
    return new_count


def query_analyses(
    results_dir: Path | str,
    *,
    ticker: Optional[str] = None,
    rating: Optional[str] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Filtered query against the index. Returns plain dicts (Streamlit-friendly).

    ``since`` is an ISO date string (YYYY-MM-DD); matched against ``trade_date``.
    """
    results_dir = Path(results_dir)
    if not _db_path(results_dir).exists():
        return []

    sql = "SELECT * FROM analyses WHERE 1=1"
    params: list = []
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    if rating:
        sql += " AND rating = ?"
        params.append(rating)
    if since:
        sql += " AND trade_date >= ?"
        params.append(since)
    sql += " ORDER BY trade_date DESC, ticker ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with _connect(results_dir) as conn:
        _init_schema(conn)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def set_note(results_dir: Path | str, ticker: str, trade_date: str, note: str) -> None:
    """更新一条分析的用户备注（Stage 8）。"""
    results_dir = Path(results_dir)
    with _connect(results_dir) as conn:
        _init_schema(conn)
        conn.execute(
            "UPDATE analyses SET note = ? WHERE ticker = ? AND trade_date = ?",
            (note, ticker, trade_date),
        )


def get_note(results_dir: Path | str, ticker: str, trade_date: str) -> str:
    """读取一条分析的用户备注；不存在则返回空串。"""
    results_dir = Path(results_dir)
    if not _db_path(results_dir).exists():
        return ""
    with _connect(results_dir) as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT note FROM analyses WHERE ticker = ? AND trade_date = ?",
            (ticker, trade_date),
        ).fetchone()
        return (row["note"] if row and row["note"] else "")


def list_tickers(results_dir: Path | str) -> list[str]:
    """Return distinct tickers in the index, sorted."""
    results_dir = Path(results_dir)
    if not _db_path(results_dir).exists():
        return []
    with _connect(results_dir) as conn:
        _init_schema(conn)
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM analyses ORDER BY ticker ASC"
        ).fetchall()
        return [r["ticker"] for r in rows]


def stats(results_dir: Path | str) -> dict:
    """High-level counts: total analyses, distinct tickers, by-rating breakdown."""
    results_dir = Path(results_dir)
    if not _db_path(results_dir).exists():
        return {"total": 0, "tickers": 0, "by_rating": {}}

    with _connect(results_dir) as conn:
        _init_schema(conn)
        total = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        tickers = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM analyses"
        ).fetchone()[0]
        by_rating = {
            r["rating"] or "Unknown": r["c"]
            for r in conn.execute(
                "SELECT rating, COUNT(*) AS c FROM analyses GROUP BY rating"
            )
        }
    return {"total": total, "tickers": tickers, "by_rating": by_rating}
