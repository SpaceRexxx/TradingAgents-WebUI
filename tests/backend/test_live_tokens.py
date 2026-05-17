from __future__ import annotations

from uuid import uuid4

from backend.services.live_tokens import (
    LiveTokenCallback,
    _infer_agent_key,
    _infer_agent_key_from_output,
)


EMBEDDED_REPORTS = """
市场研究报告: 市场与技术面分析显示震荡。
社交媒体情绪报告: 东方财富千股千评 StockTwits 雪球讨论流 都有分歧。
最新世界动态新闻: 公司与宏观经济新闻分析认为外部环境复杂。
公司基本面报告: 基本面分析 三大财务报表 显示盈利承压。
"""


def test_downstream_role_prompt_wins_over_embedded_analyst_reports():
    cases = [
        ("你是一名多头分析师，倡导投资该股票。\n" + EMBEDDED_REPORTS, "bull"),
        ("你是一名空头分析师，任务是提出反对投资该股票的论据。\n" + EMBEDDED_REPORTS, "bear"),
        ("作为高级研究经理和投资委员会主席，你的职责是批判性地评估当前的投资辩论。\n" + EMBEDDED_REPORTS, "research_manager"),
        ("你是一名分析市场数据以做出投资决策的交易代理。\n" + EMBEDDED_REPORTS, "trader"),
        ("作为激进型风险分析师，你的角色是积极倡导高回报、高风险的机会。\n" + EMBEDDED_REPORTS, "aggressive"),
        ("作为保守型风险分析师，你的首要目标是保护资产、最小化波动。\n" + EMBEDDED_REPORTS, "conservative"),
        ("作为中立型风险分析师，你的职责是提供一个平衡的视角。\n" + EMBEDDED_REPORTS, "neutral"),
        ("作为投资组合经理（Portfolio Manager），你的任务是综合评估风险分析师团队的辩论。\n" + EMBEDDED_REPORTS, "portfolio_manager"),
    ]
    for prompt, expected in cases:
        assert _infer_agent_key(prompt) == expected


def test_portfolio_manager_prompt_wins_over_embedded_research_manager_plan():
    prompt = """
作为投资组合经理（Portfolio Manager），你的任务是综合评估风险分析师团队的辩论。

**研究经理的投资计划：**
这里包含研究经理之前的完整计划。

**风险分析师辩论历史：**
激进型分析师、保守型分析师和中立型分析师已经完成讨论。
"""
    assert _infer_agent_key(prompt) == "portfolio_manager"


def test_primary_analyst_prompts_are_still_identified():
    assert _infer_agent_key("你是一名负责分析金融市场的交易助手。") == "market"
    assert _infer_agent_key("你是一名金融市场情绪分析师。东方财富千股千评") == "social"
    assert _infer_agent_key("你是一名新闻研究员，任务是分析过去 7 天的近期新闻和趋势。") == "news"
    assert _infer_agent_key("你是一名研究员，任务是分析一家公司在过去一周的基本面信息。三大财务报表") == "fundamentals"


def test_output_prefix_can_correct_a_bad_initial_prompt_guess_before_first_emit():
    events: list[dict] = []
    callback = LiveTokenCallback(events.append, min_interval=0, min_chars=8)
    run_id = uuid4()
    callback.on_llm_start(
        {},
        ["社交媒体情绪报告: 东方财富千股千评 StockTwits 雪球讨论流"],
        run_id=run_id,
    )

    for token in ["激", "进", "型", "分", "析", "师", "，", "继续", "看多"]:
        callback.on_llm_new_token(token, run_id=run_id)

    assert events
    assert "risk_debate_state" in events[-1]
    assert events[-1]["__streaming"] == {"aggressive": True}
    assert "sentiment_report" not in events[-1]


def test_output_prefix_identifies_debate_roles():
    assert _infer_agent_key_from_output("激进型分析师，你刚才那轮信息量很大") == "aggressive"
    assert _infer_agent_key_from_output("保守型分析师: 我不同意") == "conservative"
    assert _infer_agent_key_from_output("中立型分析师认为需要平衡") == "neutral"
