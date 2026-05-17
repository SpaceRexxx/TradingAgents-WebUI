from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.token_stats import (
    TokenAccumulator,
    accumulate_cumulative,
    load_cumulative,
)


def _msg(usage=None, tool_calls=None):
    return SimpleNamespace(usage_metadata=usage, tool_calls=tool_calls or [])


def test_accumulator_keeps_running_max_and_counts_tools():
    acc = TokenAccumulator()
    acc.feed({"messages": [_msg({"input_tokens": 100, "output_tokens": 40})]})
    acc.feed({"messages": [_msg({"input_tokens": 250, "output_tokens": 90})]})
    acc.feed({"messages": [_msg(tool_calls=[{"name": "get_news"}, {"name": "get_news"}])]})
    out = acc.result("deepseek-v4-pro")
    assert out["input_tokens"] == 250
    assert out["output_tokens"] == 90
    assert out["total_tokens"] == 340
    assert out["tool_calls"] == {"get_news": 2}
    assert out["tool_call_count"] == 2
    assert out["cost_usd"] == round((250 * 1.0 + 90 * 3.0) / 1_000_000, 4)


def test_accumulator_unknown_model_zero_cost():
    acc = TokenAccumulator()
    acc.feed({"messages": [_msg({"input_tokens": 10, "output_tokens": 5})]})
    assert acc.result("mystery-model")["cost_usd"] == 0.0


def test_cumulative_roundtrip(tmp_path):
    assert load_cumulative(tmp_path)["runs"] == 0
    accumulate_cumulative(
        tmp_path,
        {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
         "cost_usd": 0.01, "tool_call_count": 3},
    )
    accumulate_cumulative(
        tmp_path,
        {"input_tokens": 200, "output_tokens": 60, "total_tokens": 260,
         "cost_usd": 0.02, "tool_call_count": 1},
    )
    cum = load_cumulative(tmp_path)
    assert cum["input_tokens"] == 300
    assert cum["total_tokens"] == 410
    assert cum["cost_usd"] == 0.03
    assert cum["tool_calls"] == 4
    assert cum["runs"] == 2


def test_cumulative_endpoint_zeros_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        resp = client.get("/api/stats/cumulative")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "cost_usd": 0.0, "tool_calls": 0, "runs": 0,
    }


def test_cumulative_endpoint_reads_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    accumulate_cumulative(
        tmp_path,
        {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12,
         "cost_usd": 0.5, "tool_call_count": 2},
    )
    with TestClient(create_app()) as client:
        body = client.get("/api/stats/cumulative").json()
    assert body["runs"] == 1
    assert body["total_tokens"] == 12
    assert body["tool_calls"] == 2
