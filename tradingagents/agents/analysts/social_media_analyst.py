from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_news,
        ]

        # ----- START: 中文翻译和指令修改 -----
        system_message = (
            "你是一名社交媒体和公司特定新闻的研究员/分析师，任务是分析特定公司在过去一周的社交媒体帖子、近期公司新闻和公众情绪。你将得到一个公司名称，你的目标是在查看社交媒体上人们对该公司的评价、分析人们每天对公司的情绪数据以及查看近期公司新闻后，撰写一份详尽的综合报告，详细说明你的分析、见解以及对交易者和投资者的影响。请使用 `get_news(query, start_date, end_date)` 工具来搜索公司特定的新闻和社交媒体讨论。请尝试查看所有可能的来源，从社交媒体到情绪数据再到新闻。不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。"
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
                    "供你参考，当前日期是 {current_date}。我们当前要分析的公司是 {ticker}",
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
            "sentiment_report": report,
            "sender": "Social Analyst",
        }

    return social_media_analyst_node