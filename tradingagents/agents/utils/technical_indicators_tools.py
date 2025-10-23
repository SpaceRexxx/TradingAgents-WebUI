from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代码"],
    indicator: Annotated[str, "需要获取分析和报告的技术指标名称"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
    look_back_days: Annotated[int, "需要回溯的天数"] = 120,
) -> str:
    """
    检索给定股票代码的技术指标。
    使用已配置的 technical_indicators 供应商。
    参数:
        symbol (str): 公司的股票代码, 例如 AAPL, TSM
        indicator (str): 需要获取分析和报告的技术指标名称
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
        look_back_days (int): 需要回溯的天数, 默认为 120
    返回:
        str: 一个格式化的字符串，包含指定股票代码和指标的技术指标数据。
    """
    return route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)