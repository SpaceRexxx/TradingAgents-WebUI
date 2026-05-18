from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    get_methodology,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # ----- START: 中文翻译和指令修改 -----
        prompt = f"""作为中立型风险分析师，你的职责是提供一个平衡的视角，权衡交易员决策或计划的潜在收益和风险。你优先考虑一种全面的方法，在评估利弊的同时，考虑更广泛的市场趋势、潜在的经济转变和多元化策略。这是交易员的决策：

{trader_decision}

你的任务是挑战激进型和保守型分析师，指出他们各自的观点在哪些地方可能过于乐观或过于谨慎。请利用以下数据源的见解来支持一个温和、可持续的策略，以调整交易员的决策：

市场研究报告: {market_research_report}
社交媒体情绪报告: {sentiment_report}
最新世界动态报告: {news_report}
公司基本面报告: {fundamentals_report}
这是当前的对话历史: {history} 这是激进型分析师的最新回应: {current_aggressive_response} 这是保守型分析师的最新回应: {current_conservative_response}。如果其他观点没有回应，不要凭空想象，只陈述你自己的观点。

通过批判性地分析双方观点来积极参与，指出激进和保守论点中的弱点，以倡导一种更平衡的方法。挑战他们的每一个论点，以说明为什么一个温和的风险策略可能两全其美，既提供增长潜力，又防范极端波动。专注于辩论，而不仅仅是呈现数据，旨在表明一个平衡的观点可以带来最可靠的结果。请像平常说话一样以对话方式输出，不要使用任何特殊格式。

**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction() + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("risk_debate")

        response = llm.invoke(prompt)

        argument = f"中立型分析师: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state, "sender": "Neutral Analyst"}

    return neutral_node