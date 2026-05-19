def test_portfolio_decision_has_optional_conviction_score():
    from tradingagents.agents.schemas import PortfolioDecision

    d = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
        self_check="sc",
    )
    assert d.conviction_score is None

    d2 = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
        conviction_score=8,
        self_check="sc",
    )
    assert d2.conviction_score == 8


def test_render_pm_decision_includes_conviction_when_present():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision

    md_without = render_pm_decision(
        PortfolioDecision(rating="Hold", executive_summary="s", investment_thesis="t", self_check="sc")
    )
    assert "Conviction" not in md_without
    assert "**Rating**: Hold" in md_without  # back-compat header preserved

    md_with = render_pm_decision(
        PortfolioDecision(
            rating="Buy", executive_summary="s", investment_thesis="t",
            conviction_score=7,
            self_check="sc",
        )
    )
    assert "**Conviction**: 7/10" in md_with


def test_conviction_score_rejects_out_of_range():
    import pytest
    from pydantic import ValidationError
    from tradingagents.agents.schemas import PortfolioDecision

    for bad in (0, 11, -5):
        with pytest.raises(ValidationError):
            PortfolioDecision(
                rating="Buy", executive_summary="s", investment_thesis="t",
                conviction_score=bad,
                self_check="sc",
            )


def test_capture_returns_markdown_and_parsed_object():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
    from tradingagents.agents.utils.structured import (
        invoke_structured_or_freetext_capture,
    )

    obj = PortfolioDecision(
        rating="Buy", executive_summary="s", investment_thesis="t",
        conviction_score=9,
        self_check="sc",
    )

    class FakeStructured:
        def invoke(self, _prompt):
            return obj

    md, parsed = invoke_structured_or_freetext_capture(
        FakeStructured(), object(), "prompt", render_pm_decision, "PM"
    )
    assert "**Rating**: Buy" in md
    assert parsed is obj


def test_capture_freetext_fallback_returns_none_object():
    from tradingagents.agents.schemas import render_pm_decision
    from tradingagents.agents.utils.structured import (
        invoke_structured_or_freetext_capture,
    )

    class FakePlain:
        def invoke(self, _prompt):
            class R:
                content = "free text decision"
            return R()

    md, parsed = invoke_structured_or_freetext_capture(
        None, FakePlain(), "prompt", render_pm_decision, "PM"
    )
    assert md == "free text decision"
    assert parsed is None


def test_capture_deepseek_none_falls_back_to_freetext():
    from tradingagents.agents.schemas import render_pm_decision
    from tradingagents.agents.utils.structured import (
        invoke_structured_or_freetext_capture,
    )

    class FakeNoneStructured:
        def invoke(self, _prompt):
            return None  # provider emitted no tool-call (DeepSeek quirk)

    class FakePlain:
        def invoke(self, _prompt):
            class R:
                content = "fallback text"
            return R()

    md, parsed = invoke_structured_or_freetext_capture(
        FakeNoneStructured(), FakePlain(), "prompt", render_pm_decision, "PM"
    )
    assert md == "fallback text"
    assert parsed is None


def test_agent_state_registers_portfolio_decision_key():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "portfolio_decision" in AgentState.__annotations__


def test_trader_proposal_requires_plan_alignment_and_self_check():
    import pytest
    from pydantic import ValidationError
    from tradingagents.agents.schemas import TraderProposal

    with pytest.raises(ValidationError):
        TraderProposal(action="Sell", reasoning="r")

    tp = TraderProposal(
        action="Sell",
        reasoning="r",
        plan_alignment="研究计划评级 Underweight → 减仓,本提案方向一致",
        self_check="☑ 行动方向与研究计划评级一致\n☑ 无未溯源数字\n☑ 已给出入场/止损\n☑ 已覆盖关键风险",
    )
    assert tp.plan_alignment
    assert tp.self_check


def test_render_trader_proposal_includes_alignment_and_selfcheck():
    from tradingagents.agents.schemas import TraderProposal, render_trader_proposal

    md = render_trader_proposal(
        TraderProposal(
            action="Sell",
            reasoning="r",
            plan_alignment="评级 Underweight → 减仓,方向一致",
            self_check="☑ 行动方向与研究计划评级一致",
        )
    )
    assert "**计划对齐**: 评级 Underweight → 减仓,方向一致" in md
    assert "**【自检】**" in md
    assert "☑ 行动方向与研究计划评级一致" in md
    assert md.rstrip().endswith("FINAL TRANSACTION PROPOSAL: **SELL**")


def test_portfolio_decision_requires_self_check():
    import pytest
    from pydantic import ValidationError
    from tradingagents.agents.schemas import PortfolioDecision

    with pytest.raises(ValidationError):
        PortfolioDecision(rating="Buy", executive_summary="s", investment_thesis="t")

    d = PortfolioDecision(
        rating="Buy", executive_summary="s", investment_thesis="t",
        self_check="☑ 结论锚定风险辩论具体证据",
    )
    assert d.self_check


def test_render_pm_decision_includes_self_check():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision

    md = render_pm_decision(
        PortfolioDecision(
            rating="Hold", executive_summary="s", investment_thesis="t",
            self_check="☑ 结论锚定风险辩论具体证据\n☑ 无未溯源数字",
        )
    )
    assert "**【自检】**" in md
    assert "☑ 结论锚定风险辩论具体证据" in md
    assert "**Rating**: Hold" in md
