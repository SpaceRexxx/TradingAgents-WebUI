import time
import json


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # ----- START: 中文翻译和指令修改 -----
        prompt = f"""作为激进型风险分析师，你的角色是积极倡导高回报、高风险的机会，强调大胆的策略和竞争优势。在评估交易员的决策或计划时，请专注于潜在的上涨空间、增长潜力和创新优势——即使这些都伴随着较高的风险。使用提供的市场数据和情绪分析来加强你的论点，并挑战相反的观点。具体来说，请直接回应保守型和中立型分析师提出的每一点，用数据驱动的反驳和有说服力的推理进行反击。指出他们的谨慎可能在哪些地方错失了关键机会，或者他们的假设可能过于保守。这是交易员的决策：

{trader_decision}

你的任务是通过质疑和批判保守与中立的立场，为交易员的决策创建一个令人信服的案例，以证明为什么你的高回报视角能提供最佳的前进道路。将以下来源的见解融入你的论点中：

市场研究报告: {market_research_report}
社交媒体情绪报告: {sentiment_report}
最新世界动态报告: {news_report}
公司基本面报告: {fundamentals_report}
这是当前的对话历史: {history} 这是保守型分析师的最新论点: {current_conservative_response} 这是中立型分析师的最新论点: {current_neutral_response}。如果其他观点没有回应，不要凭空想象，只陈述你自己的观点。

通过解决提出的任何具体担忧，反驳他们逻辑中的弱点，并断言冒险能带来超越市场常规的好处来积极参与。保持专注于辩论和说服，而不仅仅是呈现数据。挑战每一个反驳点，以强调为什么高风险方法是最佳选择。请像平常说话一样以对话方式输出，不要使用任何特殊格式。

**重要指令：你的所有分析和回复都必须使用中文撰写。**"""
        # ----- END OF MODIFICATION -----

        response = llm.invoke(prompt)

        argument = f"激进型分析师: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state, "sender": "Risky Analyst"}

    return aggressive_node
