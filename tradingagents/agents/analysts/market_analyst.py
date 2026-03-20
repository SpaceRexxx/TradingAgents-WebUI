from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_stock_data,
            get_indicators,
        ]

        # ----- START: 中文翻译和指令修改 -----
        # 强制要求并行调用，减少 API 往返次数，防止连接被重置
        system_message = (
            """你是一名负责分析金融市场的交易助手。你的任务是从以下列表中为给定的市场状况或交易策略选择**最相关的指标**。
目标是选择最多**4个**指标：
1. 移动平均线类建议选 1 个。
2. 动量类（RSI/MACD）建议选 1 个。
3. 波动类（布林带/ATR）建议选 1 个。
4. 成交量类选 1 个（如果可用）。

**重要指令：**
- **必须一次性调用所有工具**：请在你的第一条回复中**并行**发出所有指标的获取指令（例如：同时列出获取 sma、rsi、macd 的工具调用），**严禁**一个一个按顺序分批调用，以减少 API 请求轮数，防止连接超时。
- 请确保首先调用 get_stock_data 获取基础价格，并**在同一条消息中**调用 get_indicators 获取所有需要的技术指标。
- 指标名称必须完全匹配：

移动平均线: close_50_sma, close_200_sma, close_10_ema
MACD 相关: macd, macds, macdh
动量指标: rsi
波动性指标: boll, boll_ub, boll_lb, atr
成交量相关: vwma

- 请撰写一份非常详尽和细致入微的分析报告。报告结尾附带 Markdown 表格。
- **所有分析和最终报告都必须使用中文撰写。**"""
        )
        # ----- END OF MODIFICATION -----

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的人工智能助手，与其他助手协同工作。"
                    "请使用提供的工具来回答问题。尽可能在一次工具调用中提出所有需要的请求。"
                    "如果你无法完全回答，另一位分析师会接替。如果你得出了最终建议，请标注“最终交易建议：**买入/持有/卖出**”。"
                    "你可以使用以下工具：{tool_names}。\n{system_message}"
                    "当前日期：{current_date}，关注公司：{ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
            "sender": "Market Analyst",
        }

    return market_analyst_node