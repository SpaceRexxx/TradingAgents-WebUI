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
