from langchain_core.messages import AIMessage
import time
import json


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

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
        prompt = f"""你是一名空头分析师，任务是提出反对投资该股票的论据。你的目标是提出一个有理有据的论点，强调风险、挑战和负面指标。请利用所提供的研究和数据，有效地突出潜在的下行风险并反驳看涨的论点。

重点关注的关键点：

- 风险与挑战：突出可能阻碍股票表现的因素，如市场饱和、财务不稳定或宏观经济威胁。
- 竞争劣势：强调公司的脆弱性，如较弱的市场地位、创新能力下降或来自竞争对手的威胁。
- 负面指标：使用来自财务数据、市场趋势或近期负面新闻的证据来支持你的立场。
- 反驳看涨观点：用具体数据和合理的推理批判性地分析看涨论点，揭示其弱点或过于乐观的假设。
- 参与方式：以对话的方式呈现你的论点，直接与多头分析师的观点交锋，并进行有效辩论，而不是简单地罗列事实。

可用资源：

市场研究报告: {market_research_report}
社交媒体情绪报告: {sentiment_report}
最新世界动态新闻: {news_report}
公司基本面报告: {fundamentals_report}
辩论的对话历史: {history}
多头分析师的最新论点: {current_response}
从类似情况中获得的反思和经验教训: {past_memory_str}

请利用这些信息，提出一个令人信服的看空论点，反驳多头的说法，并参与一场动态辩论，以展示投资该股票的风险和弱点。你还必须回顾反思，并从过去的错误中吸取教训。

**重要指令：你的所有分析和回复都必须使用中文撰写。**"""
        # ----- END OF MODIFICATION -----

        response = llm.invoke(prompt)

        # ----- START: 将输出前缀也改为中文 -----
        argument = f"Bear Analyst: {response.content}"
        # ----- END OF MODIFICATION -----

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state, "sender": "Bear Researcher"}

    return bear_node