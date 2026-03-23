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

        # ----- START: 增强的、包含个性化指令的 prompt (v0.2.2 五级评分集成) -----
        prompt = f"""作为首席风险官和最终投资决策者，你的任务是综合评估所有分析师的辩论内容，并签署一份最终的**执行摘要与投资分析报告**。

**关键上下文信息：用户当前 {has_position} 该股票仓位。** 你的所有决策都必须基于此实盘背景。

你必须根据以下**五级专业评级体系**给出最终定论：
1. **买入 (Buy)**：基本面极佳，预期收益率显著跑赢大盘。
2. **增持 (Overweight)**：趋势向好，建议在现有基础上适度增加头寸。
3. **持有 (Hold)**：多空博弈激烈或缺乏明确催化剂，建议观望。
4. **减持 (Underweight)**：短期风险上升或增长放缓，建议收缩头寸。
5. **卖出 (Sell)**：基本面恶化或技术面破位，建议果断离场。

**报告交付结构 (严格遵循以下三部分):**

**1. 执行摘要与核心评级 (Executive Summary):**
   - **最终评级**: 必须从上述五级评级中明确选出一个。
   - **投资纪要 (Investment Thesis)**: 综述你做出此决策的最高层逻辑，提炼核心风险与收益的博弈点。

**2. 核心决策依据:**
   - 简洁地提炼激进、中立、保守三方辩论中最具影响力的证据。
   - 参考历史教训“{past_memory_str}”并说明本次如何规制风险。

**3. 最终交易计划 (针对用户“{has_position}”状态的个性化方案):**
   - **操作指引**: 明确具体的操作方向（建仓/加仓/减仓/清仓/持股不动）。
   - **关键价格位**: 完善交易员原始计划“{trader_plan}”，重新审定并给出精确的**买入/卖出区间**、**止损位 (Stop-Loss)** 以及 **第一盈利目标位 (Target)**。
   - **仓位比例**: 给出具体的仓位管理比例建议。

**4. 周期展望:**
   - **短期 (30天)** / **中期 (60天)** / **长期 (90天)** 的走势预判与操作微调建议。

---

分析师辩论历史:
{history}

**重要指令：你的所有分析和最终报告都必须使用中文撰写，且必须严格遵循上述的“执行摘要”、“核心决策依据”、“最终交易计划”结构进行组织。**"""
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