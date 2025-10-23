from langchain_core.messages import AIMessage
import time
import json


def create_safe_debator(llm):
    def safe_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # ----- START: 中文翻译和指令修改 -----
        prompt = f"""作为保守型风险分析师，你的首要目标是保护资产、最小化波动并确保稳定可靠的增长。你优先考虑稳定性、安全性和风险缓解，仔细评估潜在损失、经济衰退和市场波动。在评估交易员的决策或计划时，请批判性地审视高风险元素，指出决策可能使公司面临不当风险的地方，以及更谨慎的替代方案如何能确保长期收益。这是交易员的决策：

{trader_decision}

你的任务是积极反驳激进型和中立型分析师的论点，强调他们的观点可能忽视了潜在威胁或未能优先考虑可持续性。请直接回应他们的观点，并利用以下数据源来构建一个有说服力的案例，以支持对交易员的决策进行低风险调整：

市场研究报告: {market_research_report}
社交媒体情绪报告: {sentiment_report}
最新世界动态报告: {news_report}
公司基本面报告: {fundamentals_report}
这是当前的对话历史: {history} 这是激进型分析师的最新回应: {current_risky_response} 这是中立型分析师的最新回应: {current_neutral_response}。如果其他观点没有回应，不要凭空想象，只陈述你自己的观点。

通过质疑他们的乐观态度并强调他们可能忽视的潜在缺点来参与辩论。回应他们的每一个反驳点，以展示为什么保守立场最终是公司资产最安全的路径。专注于辩论和批判他们的论点，以证明低风险策略优于他们的方法。请像平常说话一样以对话方式输出，不要使用任何特殊格式。

**重要指令：你的所有分析和回复都必须使用中文撰写。**"""
        # ----- END OF MODIFICATION -----

        response = llm.invoke(prompt)

        argument = f"保守型分析师: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state,"sender": "Safe Analyst"}

    return safe_node