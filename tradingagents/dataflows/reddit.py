"""Reddit search fetcher for ticker-specific discussion posts.

Uses OpenCLI (https://github.com/jackwener/OpenCLI) to drive the user's
logged-in Chrome session, which bypasses Reddit's WAF challenges that
block plain HTTP clients. The OpenCLI ``reddit search`` command returns
deterministic JSON for every query.

Prerequisites (one-time setup):
  1. Install OpenCLI:                    npm install -g @jackwener/opencli
  2. Install OpenCLI Chrome extension:   chromewebstore.google.com → OpenCLI
  3. Log into Reddit in that Chrome profile
  4. Verify:                             opencli doctor

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising, so callers
never have to special-case missing data.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from typing import Iterable

logger = logging.getLogger(__name__)

_OPENCLI_BIN = "opencli"
_DEFAULT_TIMEOUT = 30.0

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _opencli_available() -> bool:
    """Return True iff the ``opencli`` binary is on PATH."""
    return shutil.which(_OPENCLI_BIN) is not None


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Call ``opencli reddit search`` for one subreddit and return parsed posts.

    Each returned dict has the OpenCLI schema:
        title, subreddit, author, score, comments, url
    """
    cmd = [
        _OPENCLI_BIN, "reddit", "search", ticker,
        "--subreddit", sub,
        "--sort", "new",
        "--time", "week",
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
        logger.debug("OpenCLI Reddit fetch timed out for r/%s · %s", sub, ticker)
        return []
    except FileNotFoundError:
        logger.warning(
            "opencli binary not found on PATH. Install with "
            "`npm install -g @jackwener/opencli` or set reddit_enabled=False."
        )
        return []

    if proc.returncode != 0:
        # OpenCLI prints helpful diagnostics to stderr; surface them at debug.
        logger.debug(
            "OpenCLI Reddit fetch failed for r/%s · %s (rc=%d): %s",
            sub, ticker, proc.returncode, (proc.stderr or "").strip()[:300],
        )
        return []

    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        logger.debug("OpenCLI returned non-JSON for r/%s · %s: %s", sub, ticker, exc)
        return []

    return data if isinstance(data, list) else []


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = _DEFAULT_TIMEOUT,
    inter_request_delay: float = 0.0,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    ``inter_request_delay`` is kept for API compatibility but is no longer
    required: OpenCLI serialises browser tab leases, so we don't need a
    sleep between subreddit calls to avoid Reddit's public-API rate limit.
    """
    if not _opencli_available():
        return (
            f"<Reddit unavailable: opencli binary not found. Install with "
            f"`npm install -g @jackwener/opencli` or set reddit_enabled=False.>"
        )

    blocks = []
    total_posts = 0
    for i, sub in enumerate(subreddits):
        if i > 0 and inter_request_delay > 0:
            time.sleep(inter_request_delay)
        posts = _fetch_subreddit(ticker, sub, limit_per_sub, timeout)
        total_posts += len(posts)
        if not posts:
            blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()} in the past 7 days>")
            continue

        lines = [f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}:"]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("comments", 0)
            author = p.get("author") or "?"
            lines.append(
                f"  [{score:>4}↑ · {comments:>3}c · u/{author}] {title}"
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subreddits)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
