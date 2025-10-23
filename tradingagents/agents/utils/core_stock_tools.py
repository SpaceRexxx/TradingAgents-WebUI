from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "公司的股票代码"],
    start_date: Annotated[str, "开始日期，格式为 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式为 yyyy-mm-dd"],
) -> str:
    """
    检索给定股票代码的股价数据 (开盘价, 最高价, 最低价, 收盘价, 成交量)。
    使用已配置的 core_stock_apis 供应商。
    参数:
        symbol (str): 公司的股票代码, 例如 AAPL, TSM
        start_date (str): 开始日期，格式为 yyyy-mm-dd
        end_date (str): 结束日期，格式为 yyyy-mm-dd
    返回:
        str: 一个格式化的字符串，包含指定股票代码在指定日期范围内的股价数据。
    """
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)