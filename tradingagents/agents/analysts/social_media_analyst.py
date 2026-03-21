from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import get_news

def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [get_news]

        system_message = (
            "你是一名社交媒体和公司特定新闻的研究员/分析师，任务是分析特定公司在过去一周的社交媒体帖子、近期公司新闻和公众情绪。\n"
            "你的目标是撰写一份详尽的综合报告，详细说明你的分析、见解以及对交易者和投资者的影响。\n"
            "请使用提供的工具来搜索新闻和社交媒体讨论。请尝试查看所有可能的来源。不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析。\n"
            "确保在报告末尾附加一个Markdown表格，以有组织地整理关键点。\n"
            "**重要指令：你的所有分析和最终报告都必须使用中文撰写。**"
        )

        agent = create_react_agent(llm, tools)

        prompt_content = f"请开始进行深入的社交情绪与新闻分析。当前日期是 {current_date}，我们当前要分析的公司是 {ticker}。注意：不需要向我交代工具调用的话语，直接输出排版精美的最终报告和表格即可。"

        result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        internal_messages = result["messages"][2:]

        return {
            "messages": internal_messages,
            "sentiment_report": final_report,
            "sender": "Social Analyst",
        }

    return social_media_analyst_node