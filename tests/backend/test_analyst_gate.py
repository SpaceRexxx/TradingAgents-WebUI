def test_analyst_gate_routes_to_research_when_all_reports_present():
    from tradingagents.graph.setup import analyst_gate_decider

    state = {
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
    }
    assert analyst_gate_decider(state) == "Bull Researcher"


def test_analyst_gate_routes_to_end_when_any_report_empty():
    from langgraph.graph import END
    from tradingagents.graph.setup import analyst_gate_decider

    state = {
        "market_report": "",  # empty
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
    }
    assert analyst_gate_decider(state) == END


def test_analyst_gate_compute_halted_analysts():
    from tradingagents.graph.setup import compute_halted_analysts

    state = {
        "market_report": "  ",  # whitespace-only counts as empty
        "sentiment_report": "s",
        "news_report": "",
        "fundamentals_report": "f",
    }
    assert compute_halted_analysts(state) == ["market", "news"]


def test_analyst_gate_compute_halted_when_all_ok():
    from tradingagents.graph.setup import compute_halted_analysts

    state = {
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
    }
    assert compute_halted_analysts(state) == []


def test_agent_state_registers_halted_analysts_key():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "halted_analysts" in AgentState.__annotations__
