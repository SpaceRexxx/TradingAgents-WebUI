from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

# 最多向 LLM 返回这么多个有效交易日的数据，防止 context 过大导致 API 断连
_MAX_TRADING_DAYS_TO_RETURN = 10


def _truncate_indicator_result(result: str, max_trading_days: int = _MAX_TRADING_DAYS_TO_RETURN) -> str:
    """截断指标结果，只保留最近 N 个有效交易日的数据行，降低 token 消耗。"""
    lines = result.split("\n")
    header_lines = []
    data_lines = []
    in_data = False

    for line in lines:
        # 识别数据行：以日期格式开头，且不是 N/A 的周末/节假日行
        if line and len(line) >= 10 and line[4] == "-" and line[7] == "-":
            in_data = True
            # 跳过非交易日占位行
            if "Not a trading day" not in line:
                data_lines.append(line)
        elif in_data:
            # 数据段结束后的附加说明文字（指标描述）
            header_lines.append(line)
        else:
            header_lines.append(line)

    # 只保留最近 max_trading_days 条有效数据
    truncated_data = data_lines[:max_trading_days]
    return "\n".join(header_lines[:3]) + "\n" + "\n".join(truncated_data)


@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代码"],
    indicator: Annotated[str, "需要获取分析和报告的技术指标名称"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
    look_back_days: Annotated[int, "需要回溯的天数"] = 15,
) -> str:
    """
    检索给定股票代码的技术指标。
    使用已配置的 technical_indicators 供应商。
    参数:
        symbol (str): 公司的股票代码, 例如 AAPL, TSM
        indicator (str): 需要获取分析和报告的技术指标名称
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
        look_back_days (int): 需要回溯的天数, 默认为 15
    返回:
        str: 一个格式化的字符串，包含指定股票代码和指标的技术指标数据。
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    indicators = [i.strip() for i in indicator.split(",") if i.strip()]
    if len(indicators) > 1:
        results = []
        for ind in indicators:
            raw = route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days)
            results.append(_truncate_indicator_result(raw))
        return "\n\n".join(results)
    raw = route_to_vendor("get_indicators", symbol, indicator.strip(), curr_date, look_back_days)
    return _truncate_indicator_result(raw)