"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.

This module preserves the project's localized (Chinese) prompt and the
``has_position`` personalization injected via global config by the WebUI,
on top of the upstream structured-output scaffold.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.config import get_config


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        # WebUI 通过 set_config 注入用户持股状态；CLI/默认情形回退到“未持有”。
        config = get_config()
        has_position = config.get("has_position", "未持有")

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"**过往决策与结果反思:**\n{past_context}\n"
            if past_context
            else "**过往决策与结果反思:** 未找到相关历史交易记忆。\n"
        )

        prompt = f"""作为投资组合经理（Portfolio Manager），你的任务是综合评估风险分析师团队的辩论，并为用户制定一份**高度个性化的、可执行的最终交易决策**。

{instrument_context}

**关键上下文：用户当前 {has_position} 该标的仓位。** 你的所有建议都必须基于这个前提进行个性化定制。

---

**评级标准**（rating 字段必须从以下评级中选择恰好一个）：
- **Buy（买入）**: 强烈信心建仓或加仓
- **Overweight（超配）**: 看好，逐步增加敞口
- **Hold（持有）**: 维持当前仓位，无须操作
- **Underweight（低配）**: 减少敞口，部分获利了结
- **Sell（卖出）**: 退出仓位或回避入场

只有当双方证据确实均衡时才选择 Hold；否则应坚定地选择一个基于辩论中最强论点的立场。

---

**字段填写要求：**

1. **executive_summary（核心决策摘要）**: 用 2-4 句话概括最终行动计划，必须基于"{has_position}"状态：
   - 若用户**未持有仓位**：给出明确的**建仓区间**（例如：在 $250-$255 美元之间分批建仓）。
   - 若用户**已持有仓位**：给出**加仓 / 减仓 / 保持**的明确建议（例如：建议在当前位置减仓50%锁定利润）。

2. **investment_thesis（投资论据）**: 详细论据，必须：
   - 总结激进 / 中立 / 保守三方最有力的论点；
   - 阐述你做出最终决策的完整逻辑；
   - 从交易员的原始提案"{trader_plan}"出发，结合辩论和用户持股状态，给出完善理由；
   - 参考历史经验教训（见下方），避免重复过去的错误。

3. **price_target（目标位 / 阻力位）**: 第一个主要阻力位或首个获利了结目标价格。
4. **stop_loss（止损位）**: 明确的止损价格（必填，除非评级为 Hold 且无明显风险）。
5. **breakout_point（突破位）**: 若价格放量突破此关键点位，可考虑加仓 / 追涨。
6. **time_horizon（时间窗口）**: 建议的持仓周期，例如 "1-3 个月"。

**三段展望字段（必须填写）：**
7. **outlook_30d（30天展望）**: 短期走势预测和价格区间，附带相应的操作微调建议。
8. **outlook_60d（60天展望）**: 中期趋势预测，点出可能影响股价的关键事件 / 财报 / 宏观节点。
9. **outlook_90d（90天展望）**: 长期趋势预测，并给出明确的加仓 / 清仓触发条件。

---

**研究经理的投资计划：**
{research_plan}

**交易员的执行提案：**
{trader_plan}

{lessons_line}
**风险分析师辩论历史：**
{history}

---

请果断决策，并将每个结论锚定在分析师辩论中的具体证据上。所有字段必须针对用户的"{has_position}"状态提供个性化建议。{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
