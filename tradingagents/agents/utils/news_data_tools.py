from langchain_core.tools import tool
from typing import Annotated, Optional
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.a_share_news import fetch_a_share_news
from tradingagents.dataflows.eastmoney_sentiment import to_a_share_code
from tradingagents.dataflows.sina_finance import fetch_sina_macro_news

@tool
def get_news(
    ticker: Annotated[str, "股票代码"],
    start_date: Annotated[str, "开始日期，格式为 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式为 yyyy-mm-dd"],
) -> str:
    """
    检索给定股票代码的新闻数据。
    A 股自动走东方财富公告 + 财联社（按公司名过滤），其它市场走 Yahoo / Alpha Vantage。
    参数:
        ticker (str): 股票代码
        start_date (str): 开始日期，格式为 yyyy-mm-dd
        end_date (str): 结束日期，格式为 yyyy-mm-dd
    返回:
        str: 一个包含新闻数据的格式化字符串。
    """
    a_share_code = to_a_share_code(ticker)
    if a_share_code is not None:
        return fetch_a_share_news(a_share_code)
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "当前日期，格式为 yyyy-mm-dd"],
    look_back_days: Annotated[Optional[int], "回溯天数；不传则使用配置默认值"] = None,
    limit: Annotated[Optional[int], "返回的最大文章数量；不传则使用配置默认值"] = None,
    ticker: Annotated[Optional[str], "当前分析标的（用于决定中文/英文宏观新闻源）"] = None,
) -> str:
    """
    检索全球宏观新闻数据。
    若当前分析标的为 A 股，自动追加新浪财经 7×24 实时快讯（中文宏观信号源），
    否则使用配置默认的 Yahoo / Alpha Vantage 英文宏观新闻。
    """
    yahoo_block = route_to_vendor("get_global_news", curr_date, look_back_days, limit)

    # A-share branch: prepend Sina news (Chinese realtime macro stream)
    if ticker and to_a_share_code(ticker) is not None:
        sina_block = fetch_sina_macro_news(limit=limit or 30)
        return f"{sina_block}\n\n---\n\n## 国际宏观（Yahoo / Alpha Vantage）\n\n{yahoo_block}"

    return yahoo_block

@tool
def get_insider_sentiment(
    ticker: Annotated[str, "公司的股票代码"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
) -> str:
    """
    检索关于一家公司的内部人士情绪信息。
    使用已配置的 news_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一份关于内部人士情绪数据的报告。
    """
    return route_to_vendor("get_insider_sentiment", ticker, curr_date)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "股票代码"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
) -> str:
    """
    检索关于一家公司的内部人士交易信息。
    使用已配置的 news_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一份关于内部人士交易数据的报告。
    """
    return route_to_vendor("get_insider_transactions", ticker, curr_date)
