import time
import json

# 导入 get_config 以便从全局配置中读取数据
from tradingagents.dataflows.config import get_config

def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        # --- 从全局配置中获取持股状态 ---
        config = get_config()
        has_position = config.get("has_position", "未持有") # 默认值为“未持有”

        company_name = state["company_of_interest"]
        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec.get("recommendation", "") + "\n\n"
        
        if not past_memory_str:
            past_memory_str = "未找到相关历史交易记忆。"

        # ----- START: 增强的、包含个性化指令的 prompt -----
        prompt = f"""作为风险管理裁判和最终决策者，你的任务是综合评估所有分析，并为用户制定一份**高度个性化的、可执行的交易计划**。

**关键上下文信息：用户当前 {has_position} 该股票仓位。** 你的所有建议都必须基于这个前提。

决策指南:
1. **总结关键论点**: 简洁地提炼激进、中立、保守三方最有力的论点。
2. **提供决策依据**: 结合辩论内容和所有数据，阐述你做出最终决策的完整逻辑。
3. **优化交易员计划**: 从交易员的原始计划“**{trader_plan}**”出发，结合辩论和用户的持股状态，形成一个更完善的最终交易策略。
4. **从历史错误中学习**: 参考历史经验教训“**{past_memory_str}**”，避免重复过去的错误。

**最终交付成果 (必须包含以下所有部分):**

**1. 核心决策:**
   - **总体建议:** 明确指出是 **买入 (Buy)**, **卖出 (Sell)**, 或 **持有 (Hold)**。
   - **核心理由:** 用一两句话总结你做出此决策的最关键原因。

**2. 具体交易执行计划 (必须根据用户“{has_position}”的状态进行个性化):**
   - **如果用户未持有仓位:** 给出具体的 **“买入/建仓区间”** (例如: 在 $250-$255 美元之间分批建仓)。
   - **如果用户已持有仓位:** 给出具体的 **“加仓/减仓/保持不变”** 的建议 (例如: 建议在当前位置减仓50%锁定利润，或在回调至$250时加仓)。
   - **止损位置 (Stop-Loss):** 给出一个明确的止损价格 (例如: 止损位设置在 $240 美元)。
   - **主要目标/阻力位 (Target/Resistance):** 指出价格可能遇到的第一个主要阻力位或你的第一个获利了结目标位。
   - **突破位置 (Breakout Point):** 指出如果价格突破哪个关键点位，可以考虑加仓或追涨 (例如: 若放量突破 $265 美元，可追加仓位)。
   - **仓位管理:** 给出仓位调整的建议 (例如: 初始仓位不超过总资金的15%，或建议将现有仓位调整至...)。

**3. 未来展望 (时间维度):**
   - **30天展望:** 预测短期走势和可能的价格区间，并给出相应的操作微调建议。
   - **60天展望:** 预测中期趋势，并点出可能影响股价的关键事件。
   - **90天展望:** 预测长期趋势，并给出在何种条件下应该加仓或清仓的明确指引。

---

**分析师辩论历史:**
{history}

---

**重要指令：你的所有分析、推理和最终决策都必须使用中文撰写，并且严格按照“核心决策”、“具体交易执行计划”、“未来展望”的结构进行组织，同时确保计划针对用户的“{has_position}”状态提供个性化建议。**"""
        # ----- END OF MODIFICATION -----
        
        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
            "sender": "Risk Judge"
        }

    return risk_manager_node