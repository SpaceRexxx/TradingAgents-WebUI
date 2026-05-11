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

        prompt = f"""作为投资组合经理和辩论主持人，你的职责是批判性地评估这一轮辩论，并做出一个明确的决定。

{instrument_context}

---

**评级标准**（从以下选择一个）：
- **Buy（买入）**: 对多头论点有强烈信心；建议建仓或加仓
- **Overweight（超配）**: 建设性看法；建议逐步增加敞口
- **Hold（持有）**: 平衡看法；建议维持当前仓位
- **Underweight（低配）**: 谨慎看法；建议减少敞口
- **Sell（卖出）**: 对空头论点有强烈信心；建议退出或回避

只有在双方证据确实均衡时才选择 Hold，否则应坚定选择一个基于最强论点的立场。

---

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
