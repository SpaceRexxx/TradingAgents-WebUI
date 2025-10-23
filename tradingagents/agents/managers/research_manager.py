import time
import json


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        # 检查并处理 past_memories 可能为 None 的情况
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec.get("recommendation", "") + "\n\n"
        
        if not past_memory_str:
            past_memory_str = "未找到相关历史交易记忆。"

        # ----- START: 中文翻译和指令修改 -----
        prompt = f"""作为投资组合经理和辩论主持人，你的职责是批判性地评估这一轮辩论，并做出一个明确的决定：同意空头分析师、同意多头分析师，或者只有在有充分理由支持的情况下才选择“持有”。

请简明扼要地总结双方的关键论点，重点关注最令人信服的证据或推理。你的建议——买入、卖出或持有——必须清晰且可操作。避免仅仅因为双方都有道理就默认选择“持有”；请坚定地选择一个基于辩论中最有力论点的立场。

此外，请为交易员制定一份详细的投资计划。该计划应包括：

你的建议：一个由最有说服力的论点支持的果断立场。
基本原理：解释为什么这些论点能引导你得出结论。
战略行动：实施该建议的具体步骤。
请考虑你在类似情况下的历史错误。利用这些见解来改进你的决策过程，确保你正在学习和进步。请以自然的对话方式呈现你的分析，不要使用特殊格式。

以下是你过去对错误的反思：
\"{past_memory_str}\"

以下是本次辩论内容：
辩论历史：
{history}

**重要指令：你的所有分析、推理、投资计划和最终决策都必须使用中文撰写。**"""
        # ----- END OF MODIFICATION -----
        
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
            "sender": "Research Manager"
        }

    return research_manager_node