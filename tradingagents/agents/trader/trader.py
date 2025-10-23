import functools
import time
import json


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            # ----- START: 修改点 1 (翻译) -----
            past_memory_str = "未找到相关历史交易记忆。"
            # ----- END OF MODIFICATION -----

        # ----- START: 修改点 2 (翻译) -----
        context = {
            "role": "user",
            "content": f"基于分析师团队的全面分析，这是一份为 {company_name} 量身定制的投资计划。该计划融合了当前技术市场趋势、宏观经济指标和社交媒体情绪的洞察。请将此计划作为评估您下一步交易决策的基础。\n\n拟议投资计划: {investment_plan}\n\n请利用这些见解，做出明智且具有战略性的决策。",
        }
        # ----- END OF MODIFICATION -----

        messages = [
            {
                "role": "system",
                # ----- START: 修改点 3 (翻译和添加指令) -----
                "content": f"""你是一名分析市场数据以做出投资决策的交易代理。根据你的分析，请提供具体的买入、卖出或持有建议。请以坚定的决策结束，并始终以英文大写格式 '初步决策建议: **BUY/HOLD/SELL**' 来结束你的回复，以确认你的建议。不要忘记利用过去的决策经验，从错误中学习。以下是你在类似情况下进行交易的一些反思和经验教训：{past_memory_str}

**重要指令：你的所有分析和最终报告都必须使用中文撰写，但结尾的交易建议格式必须保持英文大写。**""",
                # ----- END OF MODIFICATION -----
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")