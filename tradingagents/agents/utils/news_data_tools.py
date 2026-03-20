from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "股票代码"],
    start_date: Annotated[str, "开始日期，格式为 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式为 yyyy-mm-dd"],
) -> str:
    """
    检索给定股票代码的新闻数据。
    使用已配置的 news_data 供应商。
    参数:
        ticker (str): 股票代码
        start_date (str): 开始日期，格式为 yyyy-mm-dd
        end_date (str): 结束日期，格式为 yyyy-mm-dd
    返回:
        str: 一个包含新闻数据的格式化字符串。
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "当前日期，格式为 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回溯的天数"] = 7,
    limit: Annotated[int, "返回的最大文章数量"] = 5,
) -> str:
    """
    检索全球宏观新闻数据。
    使用已配置的 news_data 供应商。
    参数:
        curr_date (str): 当前日期，格式为 yyyy-mm-dd
        look_back_days (int): 回溯的天数 (默认为 7)
        limit (int): 返回的最大文章数量 (默认为 5)
    返回:
        str: 一个包含全球新闻数据的格式化字符串。
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

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
