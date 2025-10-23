from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_fundamentals(
    ticker: Annotated[str, "股票代码"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
) -> str:
    """
    检索给定股票代码的综合基本面数据。
    使用已配置的 fundamental_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一个包含综合基本面数据的格式化报告。
    """
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "股票代码"],
    freq: Annotated[str, "报告频率: 'annual' (年度) / 'quarterly' (季度)"] = "quarterly",
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"] = None,
) -> str:
    """
    检索给定股票代码的资产负债表数据。
    使用已配置的 fundamental_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        freq (str): 报告频率: 'annual' (年度) / 'quarterly' (季度) (默认为季度)
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一个包含资产负债表数据的格式化报告。
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "股票代码"],
    freq: Annotated[str, "报告频率: 'annual' (年度) / 'quarterly' (季度)"] = "quarterly",
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"] = None,
) -> str:
    """
    检索给定股票代码的现金流量表数据。
    使用已配置的 fundamental_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        freq (str): 报告频率: 'annual' (年度) / 'quarterly' (季度) (默认为季度)
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一个包含现金流量表数据的格式化报告。
    """
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "股票代码"],
    freq: Annotated[str, "报告频率: 'annual' (年度) / 'quarterly' (季度)"] = "quarterly",
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"] = None,
) -> str:
    """
    检索给定股票代码的利润表数据。
    使用已配置的 fundamental_data 供应商。
    参数:
        ticker (str): 公司的股票代码
        freq (str): 报告频率: 'annual' (年度) / 'quarterly' (季度) (默认为季度)
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
    返回:
        str: 一个包含利润表数据的格式化报告。
    """
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)