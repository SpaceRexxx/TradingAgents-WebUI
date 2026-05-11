from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

# 默认向 LLM 返回的有效交易日天数（如果工具调用未指定，则使用此默认值）
_DEFAULT_TRADING_DAYS_TO_RETURN = 15


def _truncate_indicator_result(result: str, max_trading_days: int) -> str:
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
    # 注意：Yahoo 数据的历史顺序通常是日期升序，最近的在最后
    # 如果数据行很多，我们截取最后的 N 行作为“最近”的数据
    truncated_data = data_lines[-max_trading_days:] if len(data_lines) > max_trading_days else data_lines
    return "\n".join(header_lines[:3]) + "\n" + "\n".join(truncated_data)


@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代码"],
    indicator: Annotated[str, "需要获取分析和报告的技术指标名称"],
    curr_date: Annotated[str, "你正在进行交易的当前日期, 格式为 yyyy-mm-dd"],
    look_back_days: Annotated[int, "需要向回追溯自然日天数（建议与用户设置的分析窗口一致）"] = 30,
) -> str:
    """
    检索给定股票代码的技术指标。
    使用已配置的 technical_indicators 供应商。
    参数:
        symbol (str): 公司的股票代码, 例如 AAPL, TSM
        indicator (str): 需要获取分析和报告的技术指标名称
        curr_date (str): 你正在进行交易的当前日期, 格式为 yyyy-mm-dd
        look_back_days (int): 需要回溯的天数, 默认为 30。系统将根据此参数动态返回对应的交易日数据。
    返回:
        str: 一个格式化的字符串，包含指定股票代码和指标的技术指标数据。
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]

    # 我们认为 look_back_days (自然日) 对应的有效交易日大约是其 70-80%
    # 直接使用 look_back_days 作为截断上限是安全的，因为 history 拉取本身就受限于该天数
    max_to_return = look_back_days if look_back_days > 0 else _DEFAULT_TRADING_DAYS_TO_RETURN

    results = []
    for ind in indicators:
        try:
            raw = route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days)
            results.append(_truncate_indicator_result(raw, max_to_return))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)
