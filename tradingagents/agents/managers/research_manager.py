"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f'请务必考虑你过去在类似情况下的历史教训：\n"{past_context}"\n\n'
            if past_context
            else ""
        )

        prompt = f"""作为高级研究经理和投资委员会主席，你的职责是批判性地评估当前的投资辩论，并产出一份具有深度和前瞻性的投资计划。

{instrument_context}

---

**五级专业评级体系**（rating 字段必须从以下评级中选择恰好一个）：
1. **Buy（买入）**：基本面极佳，预期收益率显著跑赢大盘；建议建仓或加仓。
2. **Overweight（增持）**：趋势向好，建议在现有基础上适度增加头寸。
3. **Hold（持有）**：多空博弈激烈或缺乏明确催化剂，建议观望维持当前仓位。
4. **Underweight（减持）**：短期风险上升或增长放缓，建议收缩头寸。
5. **Sell（卖出）**：基本面恶化或技术面破位，建议果断离场或回避。

只有在双方证据确实均衡时才选择 Hold；否则应基于辩论中最有力的论点，坚定地选择一个立场。

**字段填写要求：**
- **recommendation**：从上述五级评级中明确选择一个。
- **rationale（投资逻辑 / Investment Thesis）**：简明扼要地总结多空双方的关键论点，并阐述你支持其中一方的深层逻辑。
- **strategic_actions（执行策略 / Execution Strategy）**：为交易员制定实施该建议的具体、可操作步骤，包括与评级一致的仓位指引。

{lessons_line}---

**辩论历史：**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
