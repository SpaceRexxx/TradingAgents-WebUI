from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    get_methodology,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        prompt = f"""你是一名多头分析师，倡导投资该股票。你的任务是建立一个强有力的、基于证据的案例，强调增长潜力、竞争优势和积极的市场指标。请利用所提供的研究和数据，有效回应担忧并反驳看跌的论点。

重点关注的关键点：
- 增长潜力：突出公司的市场机会、收入预测和可扩展性。
- 竞争优势：强调独特产品、强大品牌或主导市场地位等因素。
- 积极指标：使用财务健康状况、行业趋势和近期利好消息作为证据。
- 反驳看空观点：用具体数据和合理的推理批判性地分析看空论点，彻底解决担忧，并说明为什么看涨的观点更具说服力。
- 参与方式：以对话的方式呈现你的论点，直接与空头分析师的观点交锋，并进行有效辩论，而不是仅仅罗列数据。

可用资源：
市场研究报告: {market_research_report}
社交媒体情绪报告: {sentiment_report}
最新世界动态新闻: {news_report}
公司基本面报告: {fundamentals_report}
辩论的对话历史: {history}
空头分析师的最新论点: {current_response}

请利用这些信息，提出一个令人信服的看涨论点，反驳空头的担忧，并参与一场动态辩论，以展示多头立场的优势。

**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction() + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("researcher")

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state, "sender": "Bull Researcher"}

    return bull_node
