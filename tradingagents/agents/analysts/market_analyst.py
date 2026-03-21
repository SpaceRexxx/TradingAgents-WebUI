from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators

def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

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
        )
        
        # 使用隔离的 React Agent 来处理内部工具调用循环
        # 避免在并发模式下污染父图的 Global Messages 导致模型发生幻觉或崩溃
        agent = create_react_agent(llm, tools, state_modifier=system_message)
        
        prompt_content = f"请开始进行深入的市场与技术面分析。当前日期是 {current_date}，我们当前要分析的公司是 {ticker}。注意：不需要向我交代工具调用的话语，直接输出排版精美的最终报告和表格即可。"
        
        # 内部同步阻塞调用该 Agent 完成所有推导工作
        result = agent.invoke({"messages": [HumanMessage(content=prompt_content)]})
        
        # 提取最终研报大纲
        final_report = result["messages"][-1].content
        
        # 提取中间所有的工具调用日志（如果需要保留到主日志，可以塞回 messages）
        internal_messages = result["messages"][1:]

        return {
            "messages": internal_messages,
            "market_report": final_report,
            "sender": "Market Analyst",
        }

    return market_analyst_node