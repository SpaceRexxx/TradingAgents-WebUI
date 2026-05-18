from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_methodology,
    get_news,
)
from tradingagents.dataflows.eastmoney_sentiment import to_a_share_code

def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        news_lookback = state.get("news_lookback_days", 7)
        is_a_share = to_a_share_code(ticker) is not None

        tools = [get_news, get_global_news]

        if is_a_share:
            extra_a_share_instruction = (
                f"\n**A 股专属指令：** 当前标的 {ticker} 是 A 股。"
                f"调用 `get_global_news` 时请把 `ticker` 参数也设置为 \"{ticker}\"，"
                "这样会自动追加新浪财经 7×24 实时快讯（中文宏观信号源）。"
            )
        else:
            extra_a_share_instruction = ""

        system_message = (
            f"你是一名新闻研究员，任务是分析过去 {news_lookback} 天的近期新闻和趋势。请撰写一份关于当前世界状况的综合报告，内容需与交易和宏观经济相关。\n"
            "请使用提供的工具 `get_news` 检索特定公司的相关新闻，以全面了解其业务动态。如果有需要，可使用 `get_global_news` 获取广泛的宏观经济新闻。\n"
            f"重要指引：在调用工具时，请务必设置明确的日期范围，回溯天数为 {news_lookback} 天。\n"
            "不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。\n"
            "确保在报告末尾附加一个Markdown表格，以有组织地整理关键点。\n"
            "**重要指令：你的所有分析和最终报告都必须使用中文撰写。**"
            + extra_a_share_instruction
            + get_language_instruction()
            + "\n\n---\n以下是必须遵循的分析方法论:\n"
            + get_methodology("news")
        )

        agent = create_react_agent(llm, tools)

        prompt_content = (
            f"请开始进行深入的公司与宏观经济新闻分析。当前日期是 {current_date}，"
            f"分析回溯周期为 {news_lookback} 天，"
            f"我们当前要分析的公司是 {ticker}。{instrument_context}"
            "注意：不需要向我交代工具调用的话语，直接输出排版精美、分析深刻的最终报告和表格即可。"
        )

        result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        internal_messages = result["messages"][2:]

        return {
            "messages": internal_messages,
            "news_report": final_report,
            "sender": "News Analyst",
        }

    return news_analyst_node
