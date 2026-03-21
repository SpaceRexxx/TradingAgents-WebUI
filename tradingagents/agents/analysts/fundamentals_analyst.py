from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement

def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "你是一名研究员，任务是分析一家公司在过去一周的基本面信息。\n"
            "请撰写一份关于该公司基本面信息的综合报告，例如财务数据、公司简介、基本财务状况和公司财务历史，以便全面了解公司的基本面。\n"
            "请使用提供的工具获取全面的公司分析和三大财务报表。\n"
            "请确保包含尽可能多的细节。不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。\n"
            "确保在报告末尾附加一个Markdown表格，以有组织地整理关键点。\n"
            "**重要指令：你的所有分析和最终报告都必须使用中文撰写。**"
        )

        agent = create_react_agent(llm, tools, state_modifier=system_message)

        prompt_content = f"请开始进行深入的基本面分析。当前日期是 {current_date}，我们当前要分析的公司是 {ticker}。注意：不需要向我交代工具调用的话语，直接输出排版精美的最终报告和表格即可。"

        result = agent.invoke({"messages": [HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        internal_messages = result["messages"][1:]

        return {
            "messages": internal_messages,
            "fundamentals_report": final_report,
            "sender": "Fundamentals Analyst",
        }

    return fundamentals_analyst_node