import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_methodology,
    get_stock_data,
)

logger = logging.getLogger(__name__)


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        lookback_days = state.get("lookback_days", 30)

        tools = [get_stock_data, get_indicators]

        system_message = (
            "你是一名负责分析金融市场的交易助手。你的任务是从以下列表中为给定的市场状况或交易策略选择**最相关的指标**。\n"
            "目标是选择最多**4个**指标：\n"
            "1. 移动平均线类建议选 1 个。\n"
            "2. 动量类（RSI/MACD）建议选 1 个。\n"
            "3. 波动类（布林带/ATR）建议选 1 个。\n"
            "4. 成交量类选 1 个（如果可用）。\n\n"
            "**重要指令：**\n"
            "- **必须一次性调用所有工具**：请在你的第一条回复中**并行**发出所有指标的获取指令，**严禁**一个一个按顺序分批调用。\n"
            "- 请确保首先调用 get_stock_data 获取基础价格，并**在同一条消息中**调用 get_indicators 获取所有需要的技术指标。\n"
            "- 请撰写一份非常详尽和细致入微的分析报告。报告结尾附带 Markdown 表格。\n"
            "- **所有分析和最终报告都必须使用中文撰写。**"
            + get_language_instruction()
            + "\n\n---\n以下是必须遵循的分析方法论:\n"
            + get_methodology("market")
        )

        # 使用隔离的 React Agent 来处理内部工具调用循环
        # 避免在并发模式下污染父图的 Global Messages 导致模型发生幻觉或崩溃
        agent = create_react_agent(llm, tools)

        prompt_content = (
            f"请开始进行深入的市场与技术面分析。当前日期是 {current_date}，"
            f"我们当前要分析的公司是 {ticker}。{instrument_context}\n"
            f"**重要指令：**\n"
            f"1. 请在调用 `get_indicators` 工具时，将 `look_back_days` 参数显式设为 {lookback_days}。\n"
            f"2. 请在调用 `get_stock_data` 工具时，计算并设置 `start_date`，使其回溯范围至少涵盖过去 {lookback_days} 天的数据。\n"
            f"注意：不需要向我交代工具调用的话语，直接输出排版精美的中文分析报告和表格即可。"
        )


        result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        if not final_report.strip():
            logger.warning("Market Analyst: returned empty content; retrying once")
            result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})
            final_report = result["messages"][-1].content
        internal_messages = result["messages"][2:]

        return {
            "messages": internal_messages,
            "market_report": final_report,
            "sender": "Market Analyst",
        }

    return market_analyst_node
