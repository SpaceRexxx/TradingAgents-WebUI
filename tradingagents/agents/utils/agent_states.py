from typing import Annotated, Sequence
from datetime import date, timedelta, datetime
from typing_extensions import TypedDict, Optional
from langchain_openai import ChatOpenAI
from tradingagents.agents import *
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START, MessagesState


# 研究团队状态
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "看涨方对话历史"
    ]
    bear_history: Annotated[
        str, "看跌方对话历史"
    ]
    history: Annotated[str, "完整对话历史"]
    current_response: Annotated[str, "最新回应"]
    judge_decision: Annotated[str, "裁判的最终决定"]
    count: Annotated[int, "当前对话长度"]


# 风险管理团队状态
class RiskDebateState(TypedDict):
    risky_history: Annotated[
        str, "激进型代理的对话历史"
    ]
    safe_history: Annotated[
        str, "保守型代理的对话历史"
    ]
    neutral_history: Annotated[
        str, "中立型代理的对话历史"
    ]
    history: Annotated[str, "完整对话历史"]
    latest_speaker: Annotated[str, "上一位发言的分析师"]
    current_risky_response: Annotated[
        str, "激进型分析师的最新回应"
    ]
    current_safe_response: Annotated[
        str, "保守型分析师的最新回应"
    ]
    current_neutral_response: Annotated[
        str, "中立型分析师的最新回应"
    ]
    judge_decision: Annotated[str, "裁判的决定"]
    count: Annotated[int, "当前对话长度"]


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "我们感兴趣的交易公司"]
    trade_date: Annotated[str, "我们进行交易的日期"]

    sender: Annotated[str, "发送此消息的代理"]

    # 研究步骤
    market_report: Annotated[str, "来自市场分析师的报告"]
    sentiment_report: Annotated[str, "来自社交媒体分析师的报告"]
    news_report: Annotated[
        str, "来自新闻研究员关于当前世界动态的报告"
    ]
    fundamentals_report: Annotated[str, "来自基本面研究员的报告"]

    # 研究团队讨论步骤
    investment_debate_state: Annotated[
        InvestDebateState, "关于是否投资的当前辩论状态"
    ]
    investment_plan: Annotated[str, "由分析师生成的投资计划"]

    trader_investment_plan: Annotated[str, "由交易员生成的投资计划"]

    # 风险管理团队讨论步骤
    risk_debate_state: Annotated[
        RiskDebateState, "评估风险的当前辩论状态"
    ]
    final_trade_decision: Annotated[str, "由风险分析师做出的最终交易决策"]