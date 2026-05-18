from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.token_stats import (
    TokenAccumulator,
    TokenUsageCallback,
    accumulate_cumulative,
    load_cumulative,
)


def _msg(usage=None, tool_calls=None, content="", id=None):
    return SimpleNamespace(usage_metadata=usage, tool_calls=tool_calls or [], content=content, id=id)


def test_accumulator_sums_unique_usage_and_counts_tools_once():
    acc = TokenAccumulator()
    msg1 = _msg({"input_tokens": 100, "output_tokens": 40}, content="a", id="m1")
    msg2 = _msg({"input_tokens": 250, "output_tokens": 90}, content="b", id="m2")
    acc.feed({"messages": [msg1]})
    acc.feed({"messages": [msg1, msg2]})
    acc.feed({"messages": [msg1, msg2]})
    acc.feed({"messages": [_msg(tool_calls=[{"id": "t1", "name": "get_news"}, {"id": "t1", "name": "get_news"}])]})
    out = acc.result("deepseek-v4-pro")
    assert out["input_tokens"] == 350
    assert out["output_tokens"] == 130
    assert out["total_tokens"] == 480
    assert out["tool_calls"] == {"get_news": 1}
    assert out["tool_call_count"] == 1
    assert out["cost_usd"] == round((350 * 1.0 + 130 * 3.0) / 1_000_000, 4)


def test_accumulator_unknown_model_zero_cost():
    acc = TokenAccumulator()
    acc.feed({"messages": [_msg({"input_tokens": 10, "output_tokens": 5})]})
    assert acc.result("mystery-model")["cost_usd"] == 0.0


def test_accumulator_reads_cache_tokens_from_usage_metadata():
    acc = TokenAccumulator()
    acc.feed({
        "messages": [
            _msg({
                "input_tokens": 100,
                "output_tokens": 20,
                "input_token_details": {"cache_read": 30, "cache_miss": 70},
            }, id="m-cache")
        ]
    })
    out = acc.result("deepseek-v4-pro")
    assert out["input_tokens"] == 100
    assert out["cached_input_tokens"] == 30
    assert out["uncached_input_tokens"] == 70


def test_accumulator_reads_openai_token_usage_from_response_metadata():
    msg = SimpleNamespace(
        usage_metadata=None,
        response_metadata={
            "token_usage": {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
                "prompt_cache_hit_tokens": 5,
                "prompt_cache_miss_tokens": 7,
            }
        },
        tool_calls=[],
        content="x",
        id="response-meta",
    )
    acc = TokenAccumulator()
    acc.feed({"messages": [msg]})
    out = acc.result("deepseek-v4-pro")
    assert out["input_tokens"] == 12
    assert out["output_tokens"] == 7
    assert out["cached_input_tokens"] == 5
    assert out["uncached_input_tokens"] == 7


def test_token_usage_callback_reads_llm_result_llm_output():
    acc = TokenAccumulator()
    cb = TokenUsageCallback(acc)
    response = SimpleNamespace(
        generations=[],
        llm_output={
            "token_usage": {
                "prompt_tokens": 300,
                "completion_tokens": 40,
                "total_tokens": 340,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 220,
            }
        },
    )
    cb.on_llm_end(response, run_id="run-1")
    out = acc.result("deepseek-v4-pro")
    assert out["input_tokens"] == 300
    assert out["output_tokens"] == 40
    assert out["cached_input_tokens"] == 80
    assert out["uncached_input_tokens"] == 220


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
