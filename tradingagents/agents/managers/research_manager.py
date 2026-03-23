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

        # ----- START: 中文翻译和指令修改 (v0.2.2 五级评分集成) -----
        prompt = f"""作为高级研究经理和投资委员会主席，你的职责是批判性地评估当前的投资辩论，并产出一份具有深度和前瞻性的投资计划。

你的建议不再局限于简单的买或卖，而必须从以下**五级专业评级体系**中选择其一：
1. **买入 (Buy)**：基本面极佳，预期收益率显著跑赢大盘。
2. **增持 (Overweight)**：趋势向好，建议在现有基础上适度增加头寸。
3. **持有 (Hold)**：多空博弈激烈或缺乏明确催化剂，建议观望。
4. **减持 (Underweight)**：短期风险上升或增长放缓，建议收缩头寸。
5. **卖出 (Sell)**：基本面恶化或技术面破位，建议果断离场。

请基于辩论中最有力的论点，坚定地选择一个立场。你的交付成果必须包括：

- **核心评级**：从上述五级评级中明确选择一个。
- **投资逻辑 (Investment Thesis)**：简明扼要地总结多空双方的关键论点，并阐述你支持其中一方的深层逻辑。
- **执行策略 (Execution Strategy)**：为交易员制定实施该建议的具体、可操作步骤。

请务必考虑你过去在类似情况下的历史教训：
"{past_memory_str}"

以下是本次辩论历史：
{history}

**重要指令：你的所有分析、推理、投资计划和最终决策都必须使用中文撰写，且必须严格遵循上述的“核心评级”、“投资逻辑”、“执行策略”结构。**"""
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