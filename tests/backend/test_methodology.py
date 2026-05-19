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


def test_fundamentals_methodology_tightened():
    text = get_methodology("fundamentals")
    assert "实值优先" in text
    assert "估算·非工具直接读取" in text
    assert "指标 | 数值 | 期间 | 来源(工具/报表) | 实值或估算" in text
    assert "【自检】" in text
    assert "期间强制" in text


def test_sentiment_methodology_has_selfcheck_block():
    text = get_methodology("sentiment")
    assert "## 输出末尾自检" in text
    assert "【自检】" in text
    assert "每个情绪结论可回溯到注入的数据块" in text


def test_trader_pm_methodology_reference_structured_selfcheck():
    t = get_methodology("trader")
    assert "self_check" in t
    assert "plan_alignment" in t
    assert "【自检】" in t  # Phase A invariant kept
    p = get_methodology("portfolio_manager")
    assert "self_check" in p
    assert "【自检】" in p
