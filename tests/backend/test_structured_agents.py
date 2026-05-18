def test_portfolio_decision_has_optional_conviction_score():
    from tradingagents.agents.schemas import PortfolioDecision

    d = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
    )
    assert d.conviction_score is None

    d2 = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
        conviction_score=8,
    )
    assert d2.conviction_score == 8


def test_render_pm_decision_includes_conviction_when_present():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision

    md_without = render_pm_decision(
        PortfolioDecision(rating="Hold", executive_summary="s", investment_thesis="t")
    )
    assert "Conviction" not in md_without
    assert "**Rating**: Hold" in md_without  # back-compat header preserved

    md_with = render_pm_decision(
        PortfolioDecision(
            rating="Buy", executive_summary="s", investment_thesis="t",
            conviction_score=7,
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
            )
