"""Unit tests for analyst nodes' inline auto-retry-once on empty output."""
import logging
from unittest.mock import MagicMock


def test_market_analyst_auto_retries_once_on_empty(monkeypatch, caplog):
    from tradingagents.agents.analysts import market_analyst as ma

    calls = {"n": 0}
    def fake_invoke(_arg):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"messages": [MagicMock(content="")]}
        return {"messages": [MagicMock(content="REAL MARKET REPORT")]}

    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = fake_invoke
    monkeypatch.setattr(ma, "create_react_agent", lambda *_a, **_kw: fake_agent)

    node = ma.create_market_analyst(MagicMock())
    with caplog.at_level(logging.WARNING):
        out = node({"trade_date": "2026-05-20", "company_of_interest": "TEST", "lookback_days": 30})
    assert out["market_report"] == "REAL MARKET REPORT"
    assert calls["n"] == 2
    assert any("empty" in r.message.lower() and "retry" in r.message.lower() for r in caplog.records)


def test_market_analyst_still_empty_after_retry(monkeypatch, caplog):
    from tradingagents.agents.analysts import market_analyst as ma
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {"messages": [MagicMock(content="")]}
    monkeypatch.setattr(ma, "create_react_agent", lambda *_a, **_kw: fake_agent)
    node = ma.create_market_analyst(MagicMock())
    with caplog.at_level(logging.WARNING):
        out = node({"trade_date": "2026-05-20", "company_of_interest": "TEST", "lookback_days": 30})
    assert out["market_report"] == ""
    assert fake_agent.invoke.call_count == 2
    assert any("empty" in r.message.lower() for r in caplog.records)


def test_news_analyst_auto_retries_once_on_empty(monkeypatch):
    from tradingagents.agents.analysts import news_analyst as na
    calls = {"n": 0}
    def fake_invoke(_arg):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"messages": [MagicMock(content="")]}
        return {"messages": [MagicMock(content="REAL NEWS REPORT")]}
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = fake_invoke
    monkeypatch.setattr(na, "create_react_agent", lambda *_a, **_kw: fake_agent)
    node = na.create_news_analyst(MagicMock())
    out = node({"trade_date": "2026-05-20", "company_of_interest": "TEST", "news_lookback_days": 7})
    assert out["news_report"] == "REAL NEWS REPORT"
    assert calls["n"] == 2


def test_fundamentals_analyst_auto_retries_once_on_empty(monkeypatch):
    from tradingagents.agents.analysts import fundamentals_analyst as fa
    calls = {"n": 0}
    def fake_invoke(_arg):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"messages": [MagicMock(content="")]}
        return {"messages": [MagicMock(content="REAL FUNDAMENTALS REPORT")]}
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = fake_invoke
    monkeypatch.setattr(fa, "create_react_agent", lambda *_a, **_kw: fake_agent)
    node = fa.create_fundamentals_analyst(MagicMock())
    out = node({"trade_date": "2026-05-20", "company_of_interest": "TEST"})
    assert out["fundamentals_report"] == "REAL FUNDAMENTALS REPORT"
    assert calls["n"] == 2


def test_sentiment_analyst_auto_retries_once_on_empty(monkeypatch):
    """Sentiment analyst uses ChatPromptTemplate | llm chain; mock chain.invoke.

    We monkeypatch ChatPromptTemplate so that `prompt | llm` returns our
    FakeChain directly, bypassing LangChain's Runnable coercion check on llm.
    """
    from tradingagents.agents.analysts import sentiment_analyst as sa
    from langchain_core.prompts import ChatPromptTemplate

    # Sentiment pre-fetches data and builds a chain; we monkeypatch the data
    # fetchers to no-ops (empty strings).
    monkeypatch.setattr(sa, "fetch_stocktwits_messages", lambda *_a, **_kw: "")
    monkeypatch.setattr(sa, "fetch_reddit_posts", lambda *_a, **_kw: "")
    monkeypatch.setattr(sa, "fetch_xueqiu_comments", lambda *_a, **_kw: "")
    monkeypatch.setattr(sa, "fetch_eastmoney_sentiment", lambda *_a, **_kw: "")
    monkeypatch.setattr(sa, "get_news", MagicMock(return_value=""))

    calls = {"n": 0}
    def fake_chain_invoke(_messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return MagicMock(content="")
        return MagicMock(content="REAL SENTIMENT REPORT")

    class FakeChain:
        def invoke(self, messages):
            return fake_chain_invoke(messages)
        def partial(self, **_kw):
            return self
        def __or__(self, _other):
            # prompt.partial(...) | llm  -> still returns self so invoke() is ours
            return self

    # Monkeypatch ChatPromptTemplate.from_messages so it returns a FakeChain
    # that ignores the pipe-with-llm step.
    fake_chain = FakeChain()

    def fake_from_messages(*_a, **_kw):
        return fake_chain

    monkeypatch.setattr(ChatPromptTemplate, "from_messages", staticmethod(fake_from_messages))

    node = sa.create_sentiment_analyst(MagicMock())
    out = node({"trade_date": "2026-05-20", "company_of_interest": "TEST", "news_lookback_days": 7, "messages": []})
    assert out["sentiment_report"] == "REAL SENTIMENT REPORT"
    assert calls["n"] == 2
