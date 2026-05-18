"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_methodology,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一名分析市场数据以做出投资决策的交易代理。"
                    "根据你的分析，提供具体的买入、卖出或持有建议。"
                    "将你的推理锚定在分析师报告和研究计划中。"
                    + get_language_instruction()
                    + "\n\n---\n以下是必须遵循的分析方法论:\n"
                    + get_methodology("trader")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"基于分析师团队的全面分析，这是一份为 {company_name} 量身定制的投资计划。"
                    f"{instrument_context} "
                    f"该计划融合了当前技术市场趋势、宏观经济指标和社交媒体情绪的洞察。"
                    f"请将此计划作为评估你下一步交易决策的基础。\n\n"
                    f"Proposed Investment Plan（拟议投资计划）: {investment_plan}\n\n"
                    f"请利用这些见解，做出明智且具有战略性的决策。"
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
