from functools import lru_cache
from pathlib import Path

from langchain_core.messages import HumanMessage, RemoveMessage

_METHODOLOGY_DIR = Path(__file__).resolve().parents[2] / "methodology"

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


@lru_cache(maxsize=None)
def get_methodology(key: str) -> str:
    """Return the analyst methodology markdown for ``key`` (e.g. 'market').

    Methodology lives in ``tradingagents/methodology/<key>.md`` as a single
    source of truth, kept out of the prompt code so it can be iterated and
    reviewed independently. Missing/unreadable file returns "" so a
    deployment without the file degrades gracefully instead of crashing.
    Result is cached: files are read once per process.
    Missing files are also cached, so adding a methodology file mid-process requires a restart or get_methodology.cache_clear().
    """
    path = _METHODOLOGY_DIR / f"{key}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
