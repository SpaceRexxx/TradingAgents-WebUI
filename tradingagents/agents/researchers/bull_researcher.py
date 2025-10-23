from langchain_core.messages import AIMessage
import time
import json


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec.get("recommendation", "") + "\n\n"
        
        if not past_memory_str:
            past_memory_str = "未找到相关历史交易记忆。"

        # ----- START: 中文翻译和指令修改 -----
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
从类似情况中获得的反思和经验教训: {past_memory_str}

请利用这些信息，提出一个令人信服的看涨论点，反驳空头的担忧，并参与一场动态辩论，以展示多头立场的优势。你还必须回顾反思，并从过去的错误中吸取教训。

**重要指令：你的所有分析和回复都必须使用中文撰写。**"""
        # ----- END OF MODIFICATION -----

        response = llm.invoke(prompt)

        # ----- START: 将输出前缀也改为中文 -----
        argument = f"Bull Analyst: {response.content}"
        # ----- END OF MODIFICATION -----

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node