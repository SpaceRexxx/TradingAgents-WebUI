from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage
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

        # ----- START: 中文提示词 -----
        system_message = (
            """你是一名负责分析金融市场的交易助手。你的任务是从以下列表中为给定的市场状况或交易策略选择**最相关的指标**。
目标是选择最多**4个**指标：
1. 移动平均线类建议选 1 个。
2. 动量类（RSI/MACD）建议选 1 个。
3. 波动类（布林带/ATR）建议选 1 个。
4. 成交量类选 1 个（如果可用）。

**重要指令：**
- **必须一次性调用所有工具**：请在你的第一条回复中**并行**发出所有指标的获取指令（例如：同时列出获取 sma、rsi、macd 的工具调用），**严禁**一个一个按顺序分批调用。
- 请确保首先调用 get_stock_data 获取基础价格，并**在同一条消息中**调用 get_indicators 获取所有需要的技术指标。
- 请撰写一份非常详尽和细致入微的分析报告。报告结尾附带 Markdown 表格。
- **所有分析和最终报告都必须使用中文撰写。**"""
        )
        # ----- END -----

        # 【核心优化】清洗进入节点的消息历史
        # 遍历历史消息，将庞大的原始 CSV 工具输出替换为精简占位符
        messages = state["messages"]
        sanitized_messages = []
        for m in messages:
            if isinstance(m, ToolMessage):
                # 识别 get_stock_data 发出的原始 CSV 数据
                # 注意：LangChain 的 ToolMessage 有时通过 getattr(m, 'name', '') 获取工具名
                tool_name = getattr(m, "name", "")
                if tool_name == "get_stock_data" and len(str(m.content)) > 1000:
                    # 创建一个新的精简消息，保留 tool_call_id（这是 API 校验的关键）
                    m = ToolMessage(
                        content="[原始个股 CSV 数据已由系统自动清洗精简，以节省 API 带宽。指标计算已成功完成，请直接基于后续工具返回的具体指标数值进行分析。]",
                        tool_call_id=m.tool_call_id,
                        name=m.name
                    )
            sanitized_messages.append(m)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的人工智能助手，与其他助手协同工作。"
                    "请使用提供的工具来回答问题。尽可能在一次工具调用中提出所有需要的请求。"
                    "如果你得出了最终建议，请标注“最终交易建议：**买入/持有/卖出**”。"
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

        # 绑定工具
        chain = prompt | llm.bind_tools(tools)

        # 使用清洗后的消息发起调用
        result = chain.invoke(sanitized_messages)

        report = ""
        # 如果模型没有新的工具请求，说明它生成了最终报告
        if not result.tool_calls:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
            "sender": "Market Analyst",
        }

    return market_analyst_node