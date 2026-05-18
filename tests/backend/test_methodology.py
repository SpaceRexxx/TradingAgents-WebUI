from tradingagents.agents.utils.agent_utils import get_methodology


def test_get_methodology_loads_known_key():
    text = get_methodology("market")
    assert isinstance(text, str)
    assert "方法论" in text or "数据源" in text
    assert len(text) > 50


def test_get_methodology_missing_key_returns_empty_string():
    assert get_methodology("does_not_exist") == ""


def test_get_methodology_is_cached_same_object():
    a = get_methodology("fundamentals")
    b = get_methodology("fundamentals")
    assert a is b
    assert a != ""


def test_all_four_methodology_keys_present_and_nonempty():
    for key in ("market", "news", "sentiment", "fundamentals"):
        assert get_methodology(key) != "", f"missing methodology: {key}"


def test_analyst_modules_import():
    import importlib
    for mod in (
        "tradingagents.agents.analysts.market_analyst",
        "tradingagents.agents.analysts.news_analyst",
        "tradingagents.agents.analysts.fundamentals_analyst",
        "tradingagents.agents.analysts.sentiment_analyst",
    ):
        importlib.import_module(mod)


def test_phase_a_methodology_keys_present_and_nonempty():
    for key in (
        "researcher",
        "risk_debate",
        "research_manager",
        "portfolio_manager",
        "trader",
    ):
        text = get_methodology(key)
        assert text != "", f"missing methodology: {key}"
        assert "引用即纪律" in text, f"cite-or-flag rule missing in: {key}"
        assert "【自检】" in text, f"self-check block missing in: {key}"


def test_phase_a_decision_agent_modules_import():
    import importlib
    for mod in (
        "tradingagents.agents.researchers.bull_researcher",
        "tradingagents.agents.researchers.bear_researcher",
        "tradingagents.agents.risk_mgmt.aggressive_debator",
        "tradingagents.agents.risk_mgmt.conservative_debator",
        "tradingagents.agents.risk_mgmt.neutral_debator",
        "tradingagents.agents.managers.research_manager",
        "tradingagents.agents.managers.portfolio_manager",
        "tradingagents.agents.trader.trader",
    ):
        importlib.import_module(mod)
