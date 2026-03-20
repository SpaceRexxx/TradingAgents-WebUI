from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        # ----- START: 中文翻译和指令修改 -----
        system_message = (
            "你是一名研究员，任务是分析一家公司在过去一周的基本面信息。请撰写一份关于该公司基本面信息的综合报告，例如财务文件、公司简介、基本财务状况和公司财务历史，以便全面了解公司的基本面信息，为交易员提供参考。请确保包含尽可能多的细节。不要仅仅陈述趋势好坏参半，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。"
            + " 确保在报告末尾附加一个Markdown表格，以有组织、易于阅读的方式整理报告中的关键点。"
            + " 请使用可用的工具：`get_fundamentals` 用于全面的公司分析，`get_balance_sheet`（资产负债表）、`get_cashflow`（现金流量表）和 `get_income_statement`（利润表）用于获取具体的财务报表。"
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
            "fundamentals_report": report,
            "sender": "Fundamentals Analyst",
        }

    return fundamentals_analyst_node