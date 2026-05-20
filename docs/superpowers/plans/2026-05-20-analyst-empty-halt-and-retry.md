# 分析师空内容拦截 + 自动 1 次重试 + 手动重试 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 任一分析师产出空内容 → 节点内自动重试 1 次;仍空 → 主图在 Analyst Gate 处 END,持久化 halted;UI 显示 ❌ + 手动重试按钮;手动 retry 单独重跑该分析师并按需启动下游子图,同 `run_id` 全程。

**Architecture:** 不引入 LangGraph checkpointer。三层组合:① 节点内自动重试(4 analyst 文件);② 主图加 `Analyst Gate` 条件路由 + 注册 `halted_analysts` 到 AgentState + persist 标记;③ 后端 retry endpoint 重跑单 analyst,patch state,若 4 份齐则用预编译的"下游子图"(START→Bull Researcher→...→PM)继续。前端 WS 新增 `halted` event + AgentStatus `"failed"` + 重试按钮。

**Tech Stack:** Python / Pydantic / LangGraph / FastAPI / pytest;React + TypeScript + Vitest。

**参考规格:** `docs/superpowers/specs/2026-05-20-analyst-empty-halt-and-retry-design.md`

**环境注意:** `rtk` 代理过滤 pytest 输出;后端测试必须经 `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest <args> -p no:cacheprovider"`。前端测试不被过滤,正常运行。Bash 工具 cwd 在调用间保持。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**已核对基线(真实代码):**
- `tradingagents/graph/setup.py:129-130`:`workflow.add_edge(START, "Analyst Team")` + `workflow.add_edge("Analyst Team", "Bull Researcher")`(本计划改后一行为条件路由)。`"Analyst Team"` 是 4 个 analyst 并行子图,内部 `START→{Market/Social/News/Fundamentals} Analyst→END`。
- `backend/services/registry.py`:`RunStatus = {PENDING/RUNNING/DONE/ABORTED/ERROR}`;`RunHandle` 含 `queue/cancel_event/status/task/final_state/error` 与 `mark_running/mark_done/mark_error/mark_aborted/is_terminal`。
- `backend/routes/analysis.py`(prefix `/api/analysis`):registry 驱动的 endpoint 在此(start/abort/stream)。新 retry endpoint 放这里(URL 形为 `/api/analysis/{run_id}/retry-analyst`,与 spec 描述的 `/api/runs/{run_id}/retry-analyst` 等价——选择与既有 registry 路由同文件,代码就近)。
- `tradingagents/agents/utils/agent_states.py` 中 `AgentState(MessagesState)` 各字段为 `Annotated[<type>, "..."]`。新增 `halted_analysts: Annotated[list[str], "..."]`。
- 4 个 analyst 文件 invoke 形式:`market/news/fundamentals` 用 `create_react_agent(llm, tools)` + `agent.invoke({"messages": [SystemMessage, HumanMessage]})` → `result["messages"][-1].content`;`sentiment` 用 `ChatPromptTemplate.from_messages(...).partial(...) | llm` → `chain.invoke(state["messages"])` → `result.content`。
- `backend/services/persistence.py` `persist_run` 已写 `run_meta.{generated_at,model,provider,tokens,disclaimer}`;现追加 `status` 与顶层 `halted_analysts`。
- 前端 `frontend/src/util/progress.ts`:`deriveProgress(report, running, researchDepth?)` 返回 `Progress`;`AgentStatus = "pending"|"running"|"done"`,本计划增 `"failed"`。
- 前端 stream hook(`frontend/src/hooks/useAnalysisStream.ts` 一类):WS event 已处理 `done/aborted/error`,需加 `halted`。
- `frontend/src/api/types.ts`:`WsEvent` union;`AgentStatus` 在 `util/progress.ts`(导出 type)。

---

### Task 1: 4 个 analyst 节点内联自动 1 次重试

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tradingagents/agents/analysts/sentiment_analyst.py`
- Test: `tests/backend/test_analyst_auto_retry.py`(新建)

- [ ] **Step 1: 写失败测试** —— 新建 `tests/backend/test_analyst_auto_retry.py`:

```python
"""Unit tests for analyst nodes' inline auto-retry-once on empty output."""
from unittest.mock import MagicMock, patch


def _empty_then_text(empty_count: int = 1):
    """Return a fake agent.invoke that yields empty result first, then text."""
    calls = {"n": 0}

    def fake_invoke(_arg):
        calls["n"] += 1
        if calls["n"] <= empty_count:
            return {"messages": [MagicMock(content="")]}
        return {"messages": [MagicMock(content="REAL MARKET REPORT")]}

    return calls, fake_invoke


def test_market_analyst_auto_retries_once_on_empty(monkeypatch, caplog):
    import logging
    from tradingagents.agents.analysts import market_analyst as ma

    calls, fake_invoke = _empty_then_text()
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = fake_invoke
    monkeypatch.setattr(ma, "create_react_agent", lambda *_a, **_kw: fake_agent)

    node = ma.create_market_analyst(MagicMock())
    with caplog.at_level(logging.WARNING):
        out = node({
            "trade_date": "2026-05-20",
            "company_of_interest": "TEST",
            "lookback_days": 30,
        })
    assert out["market_report"] == "REAL MARKET REPORT"
    assert calls["n"] == 2  # original + 1 retry
    assert any("empty" in r.message.lower() and "retry" in r.message.lower()
               for r in caplog.records)


def test_market_analyst_still_empty_after_retry(monkeypatch):
    from tradingagents.agents.analysts import market_analyst as ma

    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {"messages": [MagicMock(content="")]}
    monkeypatch.setattr(ma, "create_react_agent", lambda *_a, **_kw: fake_agent)

    node = ma.create_market_analyst(MagicMock())
    out = node({
        "trade_date": "2026-05-20",
        "company_of_interest": "TEST",
        "lookback_days": 30,
    })
    assert out["market_report"] == ""
    assert fake_agent.invoke.call_count == 2  # tried twice
```

(News/Fundamentals/Sentiment 等价测试同形式 —— 复用 `_empty_then_text`,只换 import 与字段名。逐个 analyst 各加一组测试。实现者可按相同模式扩展;test_analyst_auto_retry.py 应至少包含上面 2 个 market 用例 + 各分析师至少 1 个"自动重试一次后产生内容"的成功路径用例。)

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_analyst_auto_retry.py -v -p no:cacheprovider"`
Expected: FAIL(当前 4 个 analyst 节点都没有自动重试逻辑;`market_report` 为 "" 时不会再调一次)。

- [ ] **Step 3: 在 4 个 analyst 文件分别加自动重试**

通用模式(以 market_analyst.py 为例):当前末尾形如:
```python
        result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})

        final_report = result["messages"][-1].content
        internal_messages = result["messages"][2:]

        return {
            "messages": internal_messages,
            "market_report": final_report,
            "sender": "Market Analyst",
        }
```
改为(在 final_report 取值后加 if-empty-retry):
```python
        result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})
        final_report = result["messages"][-1].content
        if not (final_report or "").strip():
            import logging
            logging.getLogger(__name__).warning(
                "Market Analyst: returned empty content; retrying once"
            )
            result = agent.invoke({"messages": [SystemMessage(content=system_message), HumanMessage(content=prompt_content)]})
            final_report = result["messages"][-1].content
        internal_messages = result["messages"][2:]

        return {
            "messages": internal_messages,
            "market_report": final_report,
            "sender": "Market Analyst",
        }
```

`news_analyst.py` 与 `fundamentals_analyst.py` 结构与 market 几乎一致 —— 同样在 `final_report = result["messages"][-1].content` 之后加同样的 if-empty + 重新 `agent.invoke({...})`(用各自对应的 SystemMessage/HumanMessage 与字段名 `news_report` / `fundamentals_report`,logger 文案分别为 `"News Analyst"` / `"Fundamentals Analyst"`)。

`sentiment_analyst.py` 用 `chain = prompt | llm; result = chain.invoke(state["messages"]); return {..., "sentiment_report": result.content}`。改为:
```python
        chain = prompt | llm
        result = chain.invoke(state["messages"])
        if not (result.content or "").strip():
            import logging
            logging.getLogger(__name__).warning(
                "Sentiment Analyst: returned empty content; retrying once"
            )
            result = chain.invoke(state["messages"])
        return {
            "messages": [result],
            "sentiment_report": result.content,
        }
```

- [ ] **Step 4: 运行,确认通过**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_analyst_auto_retry.py -v -p no:cacheprovider"`
Expected: 全部 PASS。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 既有全部通过 + 新测试通过,0 失败。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/agents/analysts/market_analyst.py tradingagents/agents/analysts/news_analyst.py tradingagents/agents/analysts/fundamentals_analyst.py tradingagents/agents/analysts/sentiment_analyst.py tests/backend/test_analyst_auto_retry.py
git commit -m "feat(analysts): 节点内自动一次重试空内容(4 个分析师)"
```

---

### Task 2: AgentState.halted_analysts + Analyst Gate 条件路由

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/setup.py`
- Test: `tests/backend/test_analyst_gate.py`(新建)

- [ ] **Step 1: 写失败测试** —— 新建 `tests/backend/test_analyst_gate.py`:

```python
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


def test_agent_state_registers_halted_analysts_key():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "halted_analysts" in AgentState.__annotations__
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_analyst_gate.py -v -p no:cacheprovider"`
Expected: FAIL(`analyst_gate_decider`/`compute_halted_analysts` 不存在;`halted_analysts` 未注册)。

- [ ] **Step 3: 注册 AgentState 字段**

在 `tradingagents/agents/utils/agent_states.py` 的 `AgentState` 类内,紧邻已有的 `portfolio_decision`/`past_context` 等字段位置,添加:
```python
    halted_analysts: Annotated[list[str], "分析师空内容时记录失败键列表(market/social/news/fundamentals)"]
```
(`Annotated` 与 `list` 已可用;无新增 import。)

- [ ] **Step 4: 实现 gate + 接入主图**

在 `tradingagents/graph/setup.py` 顶部 import 区(`from langgraph.graph import ...`)确保 `END` 已 import(若已 import 跳过)。在 `class GraphSetup` 之外、文件级别新增:

```python
_ANALYST_REPORT_FIELDS = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def compute_halted_analysts(state: dict) -> list[str]:
    """Return the list of analyst keys whose report is missing or whitespace-only."""
    failed: list[str] = []
    for key, field in _ANALYST_REPORT_FIELDS.items():
        val = state.get(field) or ""
        if not str(val).strip():
            failed.append(key)
    return failed


def analyst_gate_decider(state: dict) -> str:
    """Conditional routing after the Analyst Team subgraph.

    Returns ``"Bull Researcher"`` when all four analyst reports are non-empty,
    otherwise returns ``END`` (the main workflow terminates and the runner
    treats the state as halted-pending-retry).
    """
    from langgraph.graph import END
    return "Bull Researcher" if not compute_halted_analysts(state) else END
```

在 `setup_graph` 方法中,把当前:
```python
workflow.add_edge("Analyst Team", "Bull Researcher")
```
改为:
```python
workflow.add_conditional_edges(
    "Analyst Team",
    analyst_gate_decider,
    {"Bull Researcher": "Bull Researcher", END: END},
)
```

- [ ] **Step 5: 运行,确认通过**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_analyst_gate.py -v -p no:cacheprovider"`
Expected: 全部 PASS。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,0 失败。

- [ ] **Step 6: 提交**

```bash
git add tradingagents/agents/utils/agent_states.py tradingagents/graph/setup.py tests/backend/test_analyst_gate.py
git commit -m "feat(graph): Analyst Gate 条件路由 + halted_analysts 状态键注册"
```

---

### Task 3: RunHandle HALTED 状态 + retry 计数 + lock

**Files:**
- Modify: `backend/services/registry.py`
- Test: `tests/backend/test_registry_halted.py`(新建)

- [ ] **Step 1: 写失败测试** —— 新建 `tests/backend/test_registry_halted.py`:

```python
import asyncio
import pytest

from backend.services.registry import RunHandle, RunStatus


@pytest.mark.asyncio
async def test_mark_halted_sets_status_and_emits_event():
    h = RunHandle(run_id="rid")
    await h.mark_halted(["market"])
    assert h.status == RunStatus.HALTED
    ev = await asyncio.wait_for(h.queue.get(), timeout=1.0)
    assert ev == {"type": "halted", "failed_analysts": ["market"]}


def test_retry_count_initially_zero_per_analyst():
    h = RunHandle(run_id="rid")
    assert h.retry_count_by_analyst == {}
    assert h.get_retry_count("market") == 0


def test_retry_count_increments():
    h = RunHandle(run_id="rid")
    h.increment_retry("market")
    h.increment_retry("market")
    h.increment_retry("news")
    assert h.get_retry_count("market") == 2
    assert h.get_retry_count("news") == 1
    assert h.get_retry_count("fundamentals") == 0


def test_retry_lock_acquire_release():
    h = RunHandle(run_id="rid")
    assert h.try_acquire_retry_lock() is True
    assert h.try_acquire_retry_lock() is False  # already held
    h.release_retry_lock()
    assert h.try_acquire_retry_lock() is True


def test_is_terminal_includes_halted():
    h = RunHandle(run_id="rid")
    h.status = RunStatus.HALTED
    assert h.is_terminal() is True
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_registry_halted.py -v -p no:cacheprovider"`
Expected: FAIL(`HALTED`/`mark_halted`/retry 接口不存在)。

- [ ] **Step 3: 实现**

在 `backend/services/registry.py`:

(a) `RunStatus` 枚举新增 `HALTED = "halted"`。

(b) `RunHandle` 数据类追加字段:
```python
    retry_count_by_analyst: dict[str, int] = field(default_factory=dict)
    _retry_lock_held: bool = False
```
(放在 `task` 之后即可。)

(c) 新增方法:
```python
    async def mark_halted(self, failed_analysts: list[str]) -> None:
        self.status = RunStatus.HALTED
        await self.emit({"type": "halted", "failed_analysts": list(failed_analysts)})

    def get_retry_count(self, analyst: str) -> int:
        return self.retry_count_by_analyst.get(analyst, 0)

    def increment_retry(self, analyst: str) -> int:
        self.retry_count_by_analyst[analyst] = self.get_retry_count(analyst) + 1
        return self.retry_count_by_analyst[analyst]

    def try_acquire_retry_lock(self) -> bool:
        if self._retry_lock_held:
            return False
        self._retry_lock_held = True
        return True

    def release_retry_lock(self) -> None:
        self._retry_lock_held = False
```

(d) `is_terminal` 改为包含 `HALTED`:
```python
    def is_terminal(self) -> bool:
        return self.status in {RunStatus.DONE, RunStatus.ABORTED, RunStatus.ERROR, RunStatus.HALTED}
```

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_registry_halted.py -v -p no:cacheprovider"`
Expected: 全 PASS。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/services/registry.py tests/backend/test_registry_halted.py
git commit -m "feat(registry): RunHandle HALTED 状态 + retry 计数与 lock"
```

---

### Task 4: persist_run 写 halted 标记

**Files:**
- Modify: `backend/services/persistence.py`
- Test: `tests/backend/test_persistence.py`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `tests/backend/test_persistence.py` 末尾追加:

```python


def test_persist_run_writes_halted_status_and_failed_list(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 x")
    persist_run(
        results_dir=tmp_path,
        ticker="HLT",
        trade_date="2026-05-20",
        final_state={
            "market_report": "",
            "sentiment_report": "s",
            "news_report": "n",
            "fundamentals_report": "f",
            "halted_analysts": ["market"],
        },
        model="m",
        provider="p",
    )
    saved = json.loads(
        (tmp_path / "HLT" / "2026-05-20" / "final_state_report.json").read_text()
    )
    assert saved["run_meta"]["status"] == "halted"
    assert saved["halted_analysts"] == ["market"]


def test_persist_run_status_done_when_no_halted_analysts(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 x")
    persist_run(
        results_dir=tmp_path,
        ticker="OK",
        trade_date="2026-05-20",
        final_state={
            "market_report": "m", "sentiment_report": "s",
            "news_report": "n", "fundamentals_report": "f",
            "final_trade_decision": "Hold",
        },
        model="m",
        provider="p",
    )
    saved = json.loads(
        (tmp_path / "OK" / "2026-05-20" / "final_state_report.json").read_text()
    )
    assert saved["run_meta"]["status"] == "done"
    assert "halted_analysts" not in saved or saved["halted_analysts"] == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_persistence.py -k "halted or status_done" -v -p no:cacheprovider"`
Expected: FAIL(`run_meta.status` 未设置)。

- [ ] **Step 3: 实现** —— 在 `backend/services/persistence.py`,`persist_run` 的 `serializable["run_meta"] = { ... }` 块之后追加:

```python
    halted_list = list(final_state.get("halted_analysts") or [])
    serializable["run_meta"]["status"] = "halted" if halted_list else "done"
    if halted_list:
        serializable["halted_analysts"] = halted_list
```

(其它 run_meta 字段保持原样;若 `final_state` 未携带 `halted_analysts` 则状态视为 done。)

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_persistence.py -v -p no:cacheprovider"`
Expected: 全 PASS。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/services/persistence.py tests/backend/test_persistence.py
git commit -m "feat(persistence): run_meta.status + halted_analysts 标记"
```

---

### Task 5: build_downstream_workflow() —— 预编译下游子图

**Files:**
- Modify: `tradingagents/graph/setup.py`
- Test: `tests/backend/test_downstream_workflow.py`(新建)

- [ ] **Step 1: 写失败测试** —— 新建 `tests/backend/test_downstream_workflow.py`:

```python
def test_build_downstream_workflow_compiles_with_bull_as_entry():
    """The downstream subgraph must compile and have START → Bull Researcher."""
    from unittest.mock import MagicMock
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.graph.conditional_logic import ConditionalLogic

    gs = GraphSetup(
        quick_thinking_llm=MagicMock(),
        deep_thinking_llm=MagicMock(),
        tool_nodes={"market": MagicMock(), "social": MagicMock(),
                    "news": MagicMock(), "fundamentals": MagicMock()},
        conditional_logic=ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
    )
    compiled = gs.build_downstream_workflow()
    # Smoke check: compiled object exposes .invoke / .astream
    assert callable(getattr(compiled, "invoke", None))
    assert callable(getattr(compiled, "astream", None))
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_downstream_workflow.py -v -p no:cacheprovider"`
Expected: FAIL(`build_downstream_workflow` 不存在)。

- [ ] **Step 3: 实现** —— 在 `tradingagents/graph/setup.py` 的 `GraphSetup` 类中(`setup_graph` 之外)新增方法:

```python
    def build_downstream_workflow(self):
        """Compile a standalone subgraph that resumes from Bull Researcher.

        Used by the retry runner: when all four analyst reports are present
        after a retry, this subgraph runs Bull→Bear→Research Manager→Trader
        →Risk debate→Portfolio Manager on the patched state. Topology is a
        copy of the post-analyst portion of the main workflow.
        """
        from langgraph.graph import START, END, StateGraph
        from tradingagents.agents.utils.agent_states import AgentState

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        wf = StateGraph(AgentState)
        wf.add_node("Bull Researcher", bull_researcher_node)
        wf.add_node("Bear Researcher", bear_researcher_node)
        wf.add_node("Research Manager", research_manager_node)
        wf.add_node("Trader", trader_node)
        wf.add_node("Aggressive Analyst", aggressive_analyst)
        wf.add_node("Neutral Analyst", neutral_analyst)
        wf.add_node("Conservative Analyst", conservative_analyst)
        wf.add_node("Portfolio Manager", portfolio_manager_node)

        wf.add_edge(START, "Bull Researcher")
        wf.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        wf.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        wf.add_edge("Research Manager", "Trader")
        wf.add_edge("Trader", "Aggressive Analyst")
        wf.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        wf.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        wf.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        wf.add_edge("Portfolio Manager", END)
        return wf.compile()
```

注意:`conditional_logic` 的 routing dict 必须与主图 `setup_graph` 中使用的等价(实现者应核对 `setup_graph` 中 `add_conditional_edges` 的 mapping 是否一致;若主图用了不同 key,以主图为准复制)。

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_downstream_workflow.py -v -p no:cacheprovider"`
Expected: PASS。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/graph/setup.py tests/backend/test_downstream_workflow.py
git commit -m "feat(graph): build_downstream_workflow 预编译下游子图(Bull→PM)"
```

---

### Task 6: retry_runner + retry endpoint

**Files:**
- Create: `backend/services/retry_runner.py`
- Modify: `backend/routes/analysis.py`(新增 endpoint)
- Test: `tests/backend/test_retry_endpoint.py`(新建)

- [ ] **Step 1: 写失败测试** —— 新建 `tests/backend/test_retry_endpoint.py`:

```python
"""Integration tests for POST /api/analysis/{run_id}/retry-analyst."""
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.registry import RunHandle, RunStatus


def _seed_halted_run(app, *, run_id="r1", failed=("market",)):
    """Insert a halted RunHandle into the app's registry for tests."""
    registry = app.state.registry
    h = RunHandle(run_id=run_id)
    h.status = RunStatus.HALTED
    h.final_state = {
        "company_of_interest": "TST",
        "trade_date": "2026-05-20",
        "market_report": "",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "halted_analysts": list(failed),
    }
    registry._handles[run_id] = h
    return h


def test_retry_rejects_unknown_run():
    with TestClient(create_app()) as client:
        r = client.post("/api/analysis/nope/retry-analyst", json={"analyst": "market"})
        assert r.status_code == 404


def test_retry_rejects_when_run_not_halted():
    app = create_app()
    with TestClient(app) as client:
        registry = app.state.registry
        h = RunHandle(run_id="r2")
        h.status = RunStatus.RUNNING
        registry._handles["r2"] = h
        r = client.post("/api/analysis/r2/retry-analyst", json={"analyst": "market"})
        assert r.status_code == 400


def test_retry_rejects_when_lock_already_held():
    app = create_app()
    with TestClient(app) as client:
        h = _seed_halted_run(app, run_id="r3")
        h.try_acquire_retry_lock()  # simulate ongoing retry
        r = client.post("/api/analysis/r3/retry-analyst", json={"analyst": "market"})
        assert r.status_code == 409


def test_retry_rejects_when_over_limit():
    app = create_app()
    with TestClient(app) as client:
        h = _seed_halted_run(app, run_id="r4")
        for _ in range(3):
            h.increment_retry("market")
        r = client.post("/api/analysis/r4/retry-analyst", json={"analyst": "market"})
        assert r.status_code == 429


def test_retry_rejects_unknown_analyst_key():
    app = create_app()
    with TestClient(app) as client:
        _seed_halted_run(app, run_id="r5")
        r = client.post("/api/analysis/r5/retry-analyst", json={"analyst": "ghost"})
        assert r.status_code == 422 or r.status_code == 400
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_retry_endpoint.py -v -p no:cacheprovider"`
Expected: FAIL(endpoint 不存在 → 404 通过,其余因路由缺失全失败)。

- [ ] **Step 3: 实现 retry_runner**

新建 `backend/services/retry_runner.py`:
```python
"""Single-analyst retry runner used by POST /api/analysis/{run_id}/retry-analyst.

Re-invokes the failed analyst node against the existing run's final_state,
patches the report into state, and — when all four reports are non-empty —
runs the precompiled downstream subgraph (Bull Researcher → Portfolio
Manager) on the patched state. Persists with run_meta.status updated.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.services.persistence import persist_run
from backend.services.registry import RunHandle, RunStatus

logger = logging.getLogger(__name__)

ANALYST_KEYS = {"market", "social", "news", "fundamentals"}

# Map analyst key -> (factory_callable_name, report_field, label)
_FACTORY_SPECS = {
    "market": ("create_market_analyst", "market_report", "Market Analyst"),
    "social": ("create_sentiment_analyst", "sentiment_report", "Sentiment Analyst"),
    "news": ("create_news_analyst", "news_report", "News Analyst"),
    "fundamentals": ("create_fundamentals_analyst", "fundamentals_report", "Fundamentals Analyst"),
}


def _build_single_analyst_node(analyst_key: str, llm):
    """Return the node callable for `analyst_key` by importing its factory."""
    factory_name = _FACTORY_SPECS[analyst_key][0]
    if analyst_key == "market":
        from tradingagents.agents.analysts.market_analyst import create_market_analyst as f
    elif analyst_key == "social":
        from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst as f
    elif analyst_key == "news":
        from tradingagents.agents.analysts.news_analyst import create_news_analyst as f
    else:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst as f
    assert f.__name__ == factory_name
    return f(llm)


async def retry_single_analyst(
    handle: RunHandle,
    analyst_key: str,
    factory,  # callable taking nothing, returns (quick_llm, deep_llm, conditional_logic, tool_nodes, results_dir)
) -> None:
    """Re-run one analyst node, patch state, and conditionally run downstream.

    `factory` is the analysis factory used by the original run (provides the
    same LLM/tool-node bindings); the retry endpoint constructs it via the
    same path as start_analysis.
    """
    handle.increment_retry(analyst_key)
    if not handle.try_acquire_retry_lock():
        raise RuntimeError("retry_lock already held")
    try:
        state = dict(handle.final_state or {})
        quick_llm, deep_llm, _conditional_logic, _tool_nodes, results_dir = factory()
        node = _build_single_analyst_node(analyst_key, quick_llm)
        report_field = _FACTORY_SPECS[analyst_key][1]
        label = _FACTORY_SPECS[analyst_key][2]

        logger.info("Retrying analyst %s for run %s", label, handle.run_id)
        delta = await asyncio.to_thread(node, state)
        new_report = (delta or {}).get(report_field, "") or ""
        state[report_field] = new_report

        from tradingagents.graph.setup import compute_halted_analysts
        halted = compute_halted_analysts(state)
        state["halted_analysts"] = halted

        if halted:
            handle.final_state = state
            await handle.mark_halted(halted)
            await asyncio.to_thread(
                persist_run,
                results_dir,
                state.get("company_of_interest", ""),
                state.get("trade_date", ""),
                state,
            )
            return

        # All four reports now non-empty → run downstream subgraph.
        from tradingagents.graph.setup import GraphSetup
        # Reconstruct GraphSetup just to call build_downstream_workflow().
        # The retry endpoint passes the same factory used by start_analysis,
        # so quick_llm/deep_llm/conditional_logic/tool_nodes match.
        gs = GraphSetup(
            quick_thinking_llm=quick_llm,
            deep_thinking_llm=deep_llm,
            tool_nodes=_tool_nodes,
            conditional_logic=_conditional_logic,
        )
        downstream = gs.build_downstream_workflow()

        await handle.emit({"type": "status", "status": "running"})
        handle.status = RunStatus.RUNNING

        # Stream downstream chunks via the existing WS queue.
        async for chunk in downstream.astream(state):
            await handle.emit({"type": "chunk", "payload": chunk})
            state.update(chunk)  # accumulate

        handle.final_state = state
        await handle.mark_done(state)
        await asyncio.to_thread(
            persist_run,
            results_dir,
            state.get("company_of_interest", ""),
            state.get("trade_date", ""),
            state,
        )
    finally:
        handle.release_retry_lock()
```

注意:`factory()` 的签名/返回内容由 retry endpoint 在 Step 4 构造时定义;实现者需对齐 start_analysis 中既有的 graph 构造调用(在 `backend/services/runner.py` 中能找到——通常通过 `TradingAgentsGraph(config)` 等);若现有架构没有暴露一个干净的 factory,实现者应在 retry endpoint 中直接调对应构造代码而非用此简化的 `factory()` 抽象。**关键不变量**:retry 时用的 LLM/tool_nodes/conditional_logic 与原始 run 一致(否则 downstream 行为偏移)。

- [ ] **Step 4: 实现 retry endpoint**

在 `backend/routes/analysis.py` 中追加(prefix `/api/analysis` 已存在):
```python
from pydantic import BaseModel, Field as PydField

from backend.services.retry_runner import ANALYST_KEYS, retry_single_analyst


class RetryAnalystRequest(BaseModel):
    analyst: str = PydField(..., description="analyst key: market/social/news/fundamentals")


@router.post("/{run_id}/retry-analyst")
async def retry_analyst(
    run_id: str,
    body: RetryAnalystRequest,
    registry: RunRegistry = Depends(get_registry),
) -> dict:
    if body.analyst not in ANALYST_KEYS:
        raise HTTPException(status_code=422, detail=f"unknown analyst: {body.analyst}")
    handle = registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")
    from backend.services.registry import RunStatus
    if handle.status != RunStatus.HALTED:
        raise HTTPException(status_code=400, detail=f"run not halted (status={handle.status.value})")
    if handle.get_retry_count(body.analyst) >= 3:
        raise HTTPException(status_code=429, detail="retry limit reached for this analyst (max 3)")
    if not handle.try_acquire_retry_lock():
        raise HTTPException(status_code=409, detail="another retry already in progress")
    # Release immediately; retry_single_analyst will re-acquire it.
    handle.release_retry_lock()

    # Build the same factory used by start_analysis. Implementer should
    # locate the existing graph-construction helper (see runner.py / engine
    # bootstrap) and pass it here; the resulting factory must return
    # (quick_llm, deep_llm, conditional_logic, tool_nodes, results_dir).
    from backend.services.runner import build_retry_factory  # see runner.py
    factory = build_retry_factory(handle)

    handle.task = asyncio.create_task(
        retry_single_analyst(handle, body.analyst, factory),
        name=f"retry-{run_id}-{body.analyst}",
    )
    return {"run_id": run_id, "analyst": body.analyst, "retry_count": handle.get_retry_count(body.analyst) + 1}
```

并在 `backend/services/runner.py` 中暴露 `build_retry_factory(handle: RunHandle)` —— 实现者需把 start_analysis 现有的 graph 构造路径(LLM/tool_nodes/conditional_logic/results_dir)抽出复用,使 retry 用同样配置。

- [ ] **Step 5: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_retry_endpoint.py -v -p no:cacheprovider"`
Expected: 全 PASS(404/400/409/429/422 各拒绝路径)。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add backend/services/retry_runner.py backend/routes/analysis.py backend/services/runner.py tests/backend/test_retry_endpoint.py
git commit -m "feat(api): POST /api/analysis/{run_id}/retry-analyst + retry_runner"
```

---

### Task 7: 前端 — halted event + failed status + retry 按钮

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/util/progress.ts`
- Modify: `frontend/src/hooks/useAnalysisStream.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AnalysisPage.tsx`
- Test: `frontend/src/util/progress.test.ts`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `frontend/src/util/progress.test.ts` 末尾追加:

```ts

describe("deriveProgress halted state → failed analysts", () => {
  it("when streamStatus is halted and analyst content empty, status = failed", () => {
    const p = deriveProgress(
      {
        market_report: "",
        sentiment_report: "s",
        news_report: "n",
        fundamentals_report: "f",
        __halted: true,
      },
      false,
      2,
    );
    expect(p.agents.find((a) => a.key === "market")!.status).toBe("failed");
    // analysts with content still done
    expect(p.agents.find((a) => a.key === "social")!.status).toBe("done");
  });

  it("when not halted, empty analyst content is NOT failed (pending or running)", () => {
    const p = deriveProgress({ market_report: "" }, true, 2);
    expect(p.agents.find((a) => a.key === "market")!.status).not.toBe("failed");
  });
});
```

(本测试约定:halted 信号通过 `report.__halted` 透传给 `deriveProgress`,以避免改 `deriveProgress` 签名。stream hook 在收到 `halted` event 时把 `__halted: true` 注入 report;`deriveProgress` 读它判定。若实现者认为加第 4 参 `halted: boolean` 更清晰,可改测试与签名,自行保持一致。)

- [ ] **Step 2: 运行,确认失败**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: FAIL(`AgentStatus` 没有 `"failed"`;`deriveProgress` 不读 halted)。

- [ ] **Step 3: 类型 + progress 实现**

`frontend/src/api/types.ts`:
```typescript
export type AgentStatus = "pending" | "running" | "done" | "failed";

export type WsEvent =
  | { type: "running" }
  | { type: "chunk"; payload: Record<string, unknown> }
  | { type: "done"; token_stats?: Record<string, unknown> }
  | { type: "aborted" }
  | { type: "error"; message: string }
  | { type: "halted"; failed_analysts: string[] };

export interface RetryAnalystRequest { analyst: "market" | "social" | "news" | "fundamentals" }
export interface RetryAnalystResponse { run_id: string; analyst: string; retry_count: number }
```
(若 `AgentStatus` 在 `util/progress.ts` 已导出,删那边的并改为从 `api/types.ts` 导入;保持单一来源。)

`frontend/src/util/progress.ts`:
```typescript
// existing deriveProgress(...) — add at the start, after computing `contents`:
const halted = Boolean(report.__halted);

// later, after computing initial status for each agent, before returning:
if (halted) {
  for (const a of agents) {
    if (a.key in ANALYST_REPORT_KEYS && !a.content) {
      a.status = "failed";
    }
  }
}
```
(新增局部常量 `const ANALYST_REPORT_KEYS = new Set(["market", "social", "news", "fundamentals"])`。)

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: 全 PASS。

- [ ] **Step 5: stream hook + 客户端 API**

`frontend/src/hooks/useAnalysisStream.ts`(或等价 hook):在现有 `done/aborted/error` event 处理 switch 中加 case:
```typescript
case "halted":
  setStream(s => ({
    ...s,
    status: "halted",
    report: { ...s.report, __halted: true },
    failedAnalysts: event.failed_analysts,
  }));
  break;
```
(`stream.status` 类型扩展 `"halted"`;新增字段 `failedAnalysts: string[]`,初始 `[]`。)

`frontend/src/api/client.ts`:
```typescript
import type { RetryAnalystRequest, RetryAnalystResponse } from "./types";

export async function retryAnalyst(runId: string, analyst: RetryAnalystRequest["analyst"]): Promise<RetryAnalystResponse> {
  const resp = await fetch(`/api/analysis/${runId}/retry-analyst`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analyst }),
  });
  if (!resp.ok) throw new Error(`retry failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 6: AnalysisPage — banner + 重试按钮 + ❌ 图标**

`frontend/src/pages/AnalysisPage.tsx`:

(a) `statusIcon(status)` 函数增 `failed` 分支返回 `"❌"`。

(b) 在 stream 已 halted 时,渲染顶部 banner(在 agent 侧栏之上):
```tsx
{stream.status === "halted" && stream.failedAnalysts?.length > 0 && (
  <div className="card" role="alert" style={{ background:"var(--c-danger-bg, #fee)", color:"var(--c-danger, #c00)" }}>
    分析师 {stream.failedAnalysts.join("、")} 未产出报告,已暂停。请点击下方对应"重试"按钮。
  </div>
)}
```

(c) 在 progress.agents.map 渲染每个 agent 按钮时,若 `a.status === "failed"`,旁边附"重试"小按钮;点击调用 `retryAnalyst(stream.runId, a.key)`;按钮置灰条件:本地状态 `retrying === true` 或本次 run 该 analyst 已达上限(后端 429 拒绝时本地置标记 `retryExceeded[a.key] = true`,后续按钮禁用)。
```tsx
{a.status === "failed" && (
  <button
    onClick={async () => {
      setRetrying(true);
      try {
        await retryAnalyst(stream.runId, a.key as RetryAnalystRequest["analyst"]);
      } catch (e: unknown) {
        if (String(e).includes("429")) setRetryExceeded(prev => ({ ...prev, [a.key]: true }));
      } finally {
        setRetrying(false);
      }
    }}
    disabled={retrying || !!retryExceeded[a.key]}
    aria-label={`重试 ${a.label}`}
  >重试</button>
)}
```
(在组件顶部声明 `const [retrying, setRetrying] = useState(false);` 与 `const [retryExceeded, setRetryExceeded] = useState<Record<string, boolean>>({});`。)

- [ ] **Step 7: 类型检查 + 前端全量**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误。
Run: `cd frontend && npx vitest run`
Expected: 全部通过,0 失败。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/api/types.ts frontend/src/util/progress.ts frontend/src/util/progress.test.ts frontend/src/hooks/useAnalysisStream.ts frontend/src/api/client.ts frontend/src/pages/AnalysisPage.tsx
git commit -m "feat(ui): halted event + failed analyst 图标 + 重试按钮"
```

---

### Task 8: 全量回归 + 收尾

- [ ] **Step 1: 后端 + 前端全量**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,0 失败。
Run: `cd frontend && npx vitest run`
Expected: 全部通过,0 失败。
Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 2: 范围核验**

Run: `git diff --name-only HEAD~7..HEAD | sort -u`
Expected: 与本特性涉及的 ~12 个文件一致(4 analyst + agent_states + graph/setup.py + registry + persistence + retry_runner + routes/analysis + runner + 5 前端 + 测试)。无意外文件。

- [ ] **Step 3: 手动冒烟(可选,非验收门槛)**

复现 300990 类场景或人工 mock 触发市场分析师空内容(可临时在 market_analyst.py 顶部加 `if ticker=="DEBUG_EMPTY": return {"market_report": ""}`,验证完移除):
- 自动重试 1 次后仍空 → run 在 Analyst Gate halt;UI 显示 ❌ 与 banner;`final_state_report.json` 含 `run_meta.status="halted"` 与 `halted_analysts:["market"]`;下游 6 个 agent 未运行。
- 点击重试 → 后端 retry endpoint 接收;若 mock 让重试成功 → 4 份齐 → 下游子图启动 → 完成持久化 status="done";UI 状态从 halted 转 running 再转 done,❌ 转 ✓。
- 重试 3 次仍失败 → 按钮置灰。

- [ ] **Step 4: 收尾(如有遗留)**

```bash
git status --short
```
无遗留即完成;有则补一次提交。

---

## Self-Review

**Spec 覆盖:**
- 自动 1 次重试(4 个 analyst 节点内联)→ Task 1 ✅
- AgentState 注册 `halted_analysts` → Task 2 Step 3 ✅
- Analyst Gate 条件路由 + `compute_halted_analysts` + `analyst_gate_decider` → Task 2 ✅
- RunHandle HALTED + mark_halted + retry_count + retry_lock → Task 3 ✅
- `persist_run` 写 `run_meta.status` + `halted_analysts` → Task 4 ✅
- `build_downstream_workflow()` 预编译 → Task 5 ✅
- retry endpoint + retry_runner(单 analyst 重跑 + state patch + 下游子图) → Task 6 ✅
- 前端 halted event + failed 状态 + 重试按钮 + 上限置灰 → Task 7 ✅
- 端到端 retry 上限 3 + 并发 lock + run 非 halted 拒绝 + 未知 analyst 拒绝 → Task 6 测试 ✅
- 单分析师 retry 计数与自动重试计数分离 → 设计明确(自动在节点内、手动通过 endpoint;`retry_count_by_analyst` 只追踪手动) ✅
- 范围外(checkpointer / 决策类 agent / 批量 retry / 历史审计 / 自动重试次数可调)→ 计划未包含 ✅

**Placeholder 扫描:** 无 TBD/TODO 占位。Task 6 Step 3/4 含两处明确"实现者需对齐既有 graph 构造路径"的指引(`build_retry_factory` 与 LLM/tool_nodes 复用),这是真实需要 codebase 探索的工程细节,不是占位文案;实现 subagent 应按本地代码结构落地。Task 7 stream hook 的具体文件名为"或等价 hook"——实现者按真实文件名定位(项目里 stream hook 文件名可能与示例不同)。

**类型/命名一致:** `halted_analysts` 全程一致;`HALTED`/`"halted"` 在 RunStatus/WsEvent/run_meta.status/前端 stream.status 用同字面值;analyst key 全程 `"market"`/`"social"`/`"news"`/`"fundamentals"`;retry 上限 3、并发 lock、未知 key 422 在 endpoint 与测试中一致;`compute_halted_analysts` 与 `_ANALYST_REPORT_FIELDS` 在 graph/setup.py 与 retry_runner 一致引用。

**已知风险(供实现注意):**
- LangGraph 子图 `astream` 的 chunk shape 与主图 `astream` 可能略有差异;Task 6 retry_runner 中 `state.update(chunk)` 是简化合并,实现时需对齐既有 runner.py 中如何累积 chunk 至 final_state(可能用同样的 `clear_streaming_payload` 等辅助)。
- `build_retry_factory(handle: RunHandle)` 在 runner.py 中如何复用既有 `start_analysis` 的 graph 构造路径,需要实现者读 runner.py 后决定最少侵入的暴露方式(可能是抽 helper、可能是把构造结果缓存到 handle 上)。两种都可接受,选择以"不破坏既有 start_analysis 行为"为标准。
- 测试用 TestClient 直接操作 `app.state.registry` 是简化(避免起真实 graph);若 app 注册的 registry 在 lifespan 之外构造,实现者需用真实的 `Depends(get_registry)` 调用路径(可能需要把 mock registry 通过 dependency_overrides 注入)。
