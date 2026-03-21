from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import get_news, get_global_news

def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [get_news, get_global_news]

        system_message = (
            "你是一名新闻研究员，任务是分析过去一周的近期新闻和趋势。请撰写一份关于当前世界状况的综合报告，内容需与交易和宏观经济相关。\n"
            "请使用提供的工具 `get_news` 检索特定公司的相关新闻，以全面了解其业务动态。如果有需要，可使用 `get_global_news` 获取广泛的宏观经济新闻。\n"
            "不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。\n"
            "确保在报告末尾附加一个Markdown表格，以有组织地整理关键点。\n"
            "**重要指令：你的所有分析和最终报告都必须使用中文撰写。**"
        )

        agent = create_react_agent(llm, tools, state_modifier=system_message)

        prompt_content = f"请开始进行深入的公司与宏观经济新闻分析。当前日期是 {current_date}，我们当前要分析的公司是 {ticker}。注意：不需要向我交代工具调用的话语，直接输出排版精美的最终报告和表格即可。"

        result = agent.invoke({"messages": [HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        internal_messages = result["messages"][1:]

        return {
            "messages": internal_messages,
            "news_report": final_report,
            "sender": "News Analyst",
        }

    return news_analyst_node