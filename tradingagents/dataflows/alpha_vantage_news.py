from .alpha_vantage_common import _make_api_request, format_datetime_for_api
import re
from datetime import datetime, timedelta

def get_news(ticker_or_topic, start_date, end_date) -> dict[str, str] | str:
    """
    Returns live and historical market news & sentiment data.
    Intelligently handles both ticker symbols and general topics.

    Args:
        ticker_or_topic: Stock symbol (e.g., "AAPL") or a general topic (e.g., "macroeconomics").
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    params = {
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "sort": "LATEST",
        "limit": "50",
    }
    
    # 智能判断是 Ticker 还是 Topic
    # 如果输入是1-5个大写字母和可选的点(如 BRK.A)，则视为 Ticker
    if re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', ticker_or_topic):
        params["tickers"] = ticker_or_topic
    else:
        # 否则，视为通用主题
        params["topics"] = ticker_or_topic.lower().replace(" ", "_")

    return _make_api_request("NEWS_SENTIMENT", params)

# --- 新增函数 ---
def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 20) -> str:
    """
    Retrieves global macroeconomic news using the Alpha Vantage API by searching relevant topics.
    """
    # Define relevant topics for global news
    topics = "economy_macro,finance,earnings,mergers_and_acquisitions,financial_markets"

    # Calculate date range
    end_date_obj = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date_obj = end_date_obj - timedelta(days=look_back_days)
    
    start_date_str = start_date_obj.strftime("%Y-%m-%d")
    end_date_str = end_date_obj.strftime("%Y-%m-%d")

    # Reuse the intelligent get_news function
    return get_news(topics, start_date_str, end_date_str)
# --- 新增结束 ---

def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)