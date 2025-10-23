from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_news,
            get_global_news,
        ]

        # ----- START: 中文翻译和指令修改 -----
        system_message = (
            "你是一名新闻研究员，任务是分析过去一周的近期新闻和趋势。请撰写一份关于当前世界状况的综合报告，内容需与交易和宏观经济相关。请使用可用的工具：`get_news(query, start_date, end_date)` 用于公司特定或有针对性的新闻搜索，以及 `get_global_news(curr_date, look_back_days, limit)` 用于更广泛的宏观经济新闻。不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。"
            + " 确保在报告末尾附加一个Markdown表格，以有组织、易于阅读的方式整理报告中的关键点。"
            + "\n\n**重要指令：你的所有分析和最终报告都必须使用中文撰写。**"
        )
        # ----- END OF MODIFICATION -----

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的人工智能助手，与其他助手协同工作。"
                    "请使用提供的工具来逐步回答问题。"
                    "如果你无法完全回答，没关系；另一位拥有不同工具的助手会接替你未完成的部分。尽你所能去取得进展。"
                    "如果你或任何其他助手得出了最终的交易建议（例如：最终交易建议：**买入/持有/卖出**），请在你的回复前加上“最终交易建议：**买入/持有/卖出**”，以便团队知晓可以停止工作。"
                    "你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是 {current_date}。我们关注的公司是 {ticker}",
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
            "news_report": report,
            "sender": "News Analyst",
        }

    return news_analyst_node