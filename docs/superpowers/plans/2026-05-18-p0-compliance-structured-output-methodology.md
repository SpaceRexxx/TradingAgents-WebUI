# P0 升级实现计划:合规元数据 + 结构化决策表格化 + 分析师方法论外置

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 TradingAgents-WebUI 落地三项 P0 升级:分析师方法论外置为可加载 Markdown、Portfolio 决策结构化(含 conviction 评分)并在 PDF/前端表格化、报告注入合规免责声明与运行元数据。

**Architecture:** 方法论以 `tradingagents/methodology/*.md` 单一来源,运行时经 `get_methodology()` 拼进 4 个分析师 system prompt。Portfolio Manager 通过新的 capture 变体保留解析出的 `PortfolioDecision` 对象写入 `final_state["portfolio_decision"]`,PDF 与前端直接读字段渲染表格;`persist_run` 生成 `run_meta`(时间戳/模型/供应商/token摘要/免责声明)写入 JSON 并在 PDF 页脚与前端报告页呈现。markdown 渲染保留作向后兼容回退。

**Tech Stack:** Python 3 / Pydantic / LangGraph / FastAPI / pytest;React + TypeScript + Vite + Vitest。

**参考规格:** `docs/superpowers/specs/2026-05-18-p0-compliance-structured-output-methodology-design.md`

**执行修正(Task 4):** `portfolio_decision` 已注册进 `tradingagents/agents/utils/agent_states.py` 的 `AgentState` TypedDict(否则 LangGraph 会丢弃该键,Task 6/7 拿不到)。Task 6/7 实现者可放心从 `final_state["portfolio_decision"]` 读取。

**注意:** SQLite `analyses` 表已有 `created_at TEXT NOT NULL DEFAULT (datetime('now'))`(`tradingagents/storage/sqlite_history.py:76`),已满足审计时间戳需求,**无需** SQLite schema 变更;`generated_at` 仅写入 JSON `run_meta`。

---

### Task 1: 方法论加载器 + 4 个方法论文件

**Files:**
- Create: `tradingagents/methodology/market.md`
- Create: `tradingagents/methodology/news.md`
- Create: `tradingagents/methodology/sentiment.md`
- Create: `tradingagents/methodology/fundamentals.md`
- Modify: `tradingagents/agents/utils/agent_utils.py`(在 `get_language_instruction` 之后新增 `get_methodology`)
- Test: `tests/backend/test_methodology.py`

- [ ] **Step 1: 写失败测试**

Create `tests/backend/test_methodology.py`:

```python
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
    assert a == b
    assert a != ""
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `pytest tests/backend/test_methodology.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_methodology'`

- [ ] **Step 3: 新增 4 个方法论文件**

Create `tradingagents/methodology/market.md`:

```markdown
# 市场与技术面分析方法论

## 数据源优先级
1. `get_stock_data` 基础价格(必须最先调用,且与指标调用同一条消息并行发出)。
2. `get_indicators` 技术指标,`look_back_days` 必须显式设为本次回溯天数。
3. 无数据时明确写"数据缺失",严禁臆造点位或编造历史数据。

## 指标口径纪律
- 移动平均线类、动量类(RSI/MACD)、波动类(布林带/ATR)、成交量类各选≤1,合计≤4 个。
- 所有点位标注其来源指标与时间窗口;每个结论必须能追溯到具体指标读数。
- 区分"价格"与"指标信号",不得用单一指标下绝对结论。

## QC 清单(报告末尾自检)
- [ ] 每个关键点位都标注了来源指标与窗口
- [ ] 回溯窗口与用户请求的天数一致
- [ ] 结尾含 Markdown 表格,组织关键点
- [ ] 无未溯源的数字;不确定处显式标注

## 常见错误(必须规避)
- 顺序分批调用工具(应一次性并行)。
- 用单一动量指标对趋势下绝对判断。
- 把指标缺失当作中性信号而不声明。
```

Create `tradingagents/methodology/news.md`:

```markdown
# 新闻与宏观分析方法论

## 数据源优先级
1. `get_news` 检索标的相关公司新闻。
2. `get_global_news` 获取宏观经济新闻;A 股标的须把 `ticker` 一并传入以追加中文实时快讯。
3. 工具调用必须设置与回溯天数一致的明确日期范围。

## 内容纪律
- 区分"已发生事实"与"市场预期/传闻",分别标注。
- 每条对交易有影响的结论必须绑定具体新闻条目(标题/日期)。
- 不泛泛说"利好利空参半";给出可操作的细颗粒度判断。

## QC 清单
- [ ] 每个关键判断绑定了具体新闻来源
- [ ] 日期范围覆盖请求的回溯周期
- [ ] 区分了事实与预期
- [ ] 结尾含组织关键点的 Markdown 表格

## 常见错误
- 把新闻标题情绪等同于价格影响。
- 忽略宏观节点(财报/议息/数据发布)对个股的传导。
- 引用无日期、无出处的"市场消息"。
```

Create `tradingagents/methodology/sentiment.md`:

```markdown
# 舆情情绪分析方法论

## 数据源优先级与可信度
1. 机构口径:新闻头条(框架性参考)。
2. 散户口径:StockTwits(含用户标注的 Bullish/Bearish)、雪球评论。
3. 社区:Reddit(若被关闭会出现占位提示,不得据占位文本编造内容)。

## 情绪量化纪律
- 提示词内已注入的数据块是唯一可信来源;严禁补充未提供的帖子或情绪。
- 区分情绪"强度"与"方向";注意时效性与异常账号噪声。
- 数据源缺失/被关闭时,显式说明该源不可用,不得用占位符内容作结论。

## QC 清单
- [ ] 每个情绪结论可回溯到注入的数据块
- [ ] 标注了缺失/被关闭的数据源
- [ ] 区分了散户与机构口径
- [ ] 全中文,无英文章节标题

## 常见错误
- 在 Reddit 占位提示下编造社区帖子。
- 把单条高赞帖当作整体情绪。
- 忽略数据源时效与样本偏差。
```

Create `tradingagents/methodology/fundamentals.md`:

```markdown
# 基本面分析方法论

## 数据源优先级
1. `get_fundamentals` 公司概览。
2. 三大报表:`get_income_statement` / `get_balance_sheet` / `get_cashflow`。
3. `get_insider_transactions` 内部人交易作为辅助信号。

## 指标口径纪律
- 估值类(P/E、P/B、EV/EBITDA)、盈利质量(ROE、ROIC、毛/净利率)、偿债与现金流(负债率、自由现金流)分组评估,不可只看单一指标。
- 趋势优先于快照:尽量给多期变化而非单点值。
- 每个财务结论标注其来源报表与期间。

## QC 清单
- [ ] 估值/盈利/偿债现金流三组均有覆盖
- [ ] 关键数字标注来源报表与期间
- [ ] 给出趋势而非孤立快照
- [ ] 结尾含组织关键点的 Markdown 表格

## 常见错误
- 以单季数据外推全年。
- 忽略现金流与利润背离(应计质量)。
- 只看绝对估值不做同业/历史对照。
```

- [ ] **Step 4: 实现 `get_methodology`**

In `tradingagents/agents/utils/agent_utils.py`, add at the top of the file (after line 1 import) the stdlib imports, and add the function immediately after `get_language_instruction` (ends at line 36):

```python
# add near existing imports at top of file:
from functools import lru_cache
from pathlib import Path

_METHODOLOGY_DIR = Path(__file__).resolve().parents[2] / "methodology"


@lru_cache(maxsize=None)
def get_methodology(key: str) -> str:
    """Return the analyst methodology markdown for ``key`` (e.g. 'market').

    Methodology lives in ``tradingagents/methodology/<key>.md`` as a single
    source of truth, kept out of the prompt code so it can be iterated and
    reviewed independently. Missing/unreadable file returns "" so a
    deployment without the file degrades gracefully instead of crashing.
    Result is cached: files are read once per process.
    """
    path = _METHODOLOGY_DIR / f"{key}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""
```

Note: `parents[2]` resolves `tradingagents/agents/utils/agent_utils.py` → `tradingagents/`, so the dir is `tradingagents/methodology/`.

- [ ] **Step 5: 运行测试,确认通过**

Run: `pytest tests/backend/test_methodology.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 提交**

```bash
git add tradingagents/methodology/ tradingagents/agents/utils/agent_utils.py tests/backend/test_methodology.py
git commit -m "feat(agents): 方法论外置为可加载 Markdown + get_methodology 加载器"
```

---

### Task 2: 将方法论拼进 4 个分析师 system prompt

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tradingagents/agents/analysts/sentiment_analyst.py`
- Test: `tests/backend/test_methodology.py`(追加 wiring 测试)

- [ ] **Step 1: 追加失败测试**

Append to `tests/backend/test_methodology.py`:

```python
def test_all_four_methodology_keys_present_and_nonempty():
    for key in ("market", "news", "sentiment", "fundamentals"):
        assert get_methodology(key) != "", f"missing methodology: {key}"
```

- [ ] **Step 2: 运行,确认通过**(文件已在 Task 1 创建)

Run: `pytest tests/backend/test_methodology.py::test_all_four_methodology_keys_present_and_nonempty -v`
Expected: PASS

- [ ] **Step 3: market_analyst.py 接入**

In `tradingagents/agents/analysts/market_analyst.py`:
- Line 3-8 import block: add `get_methodology` to the imported names from `tradingagents.agents.utils.agent_utils`.
- The `system_message` currently ends at line 33 with `+ get_language_instruction()`. Change that tail to:

```python
            + get_language_instruction()
            + "\n\n---\n以下是必须遵循的分析方法论:\n"
            + get_methodology("market")
```

- [ ] **Step 4: news_analyst.py 接入**

In `tradingagents/agents/analysts/news_analyst.py`:
- Line 3-8 import block: add `get_methodology`.
- `system_message` tail is `+ extra_a_share_instruction + get_language_instruction()` (lines 37-38). Change to:

```python
            + extra_a_share_instruction
            + get_language_instruction()
            + "\n\n---\n以下是必须遵循的分析方法论:\n"
            + get_methodology("news")
```

- [ ] **Step 5: fundamentals_analyst.py 接入**

In `tradingagents/agents/analysts/fundamentals_analyst.py`:
- Line 3-11 import block: add `get_methodology`.
- `system_message` tail is `+ get_language_instruction()` (line 34). Change to:

```python
            + get_language_instruction()
            + "\n\n---\n以下是必须遵循的分析方法论:\n"
            + get_methodology("fundamentals")
```

- [ ] **Step 6: sentiment_analyst.py 接入**

In `tradingagents/agents/analysts/sentiment_analyst.py`:
- Lines 25-29 import block: add `get_methodology` to the names imported from `tradingagents.agents.utils.agent_utils`.
- The `_build_system_message(...)` function returns the assembled system message string (def starts at line 125). Locate its `return` statement (the final assembled string) and append the methodology before returning. Concretely, find the line that returns the f-string ending the function and wrap the return value:

```python
    # at the end of _build_system_message, change:
    #     return <existing_assembled_message>
    # to:
    _base = <existing_assembled_message>
    return _base + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("sentiment")
```

(Replace `<existing_assembled_message>` with whatever expression the function currently returns; do not change its content, only append.)

- [ ] **Step 7: 冒烟测试 — 4 个分析师模块可导入且 prompt 含方法论标记**

Add to `tests/backend/test_methodology.py`:

```python
def test_market_analyst_module_imports():
    # Import path proves get_methodology wiring did not break the module.
    import importlib
    for mod in (
        "tradingagents.agents.analysts.market_analyst",
        "tradingagents.agents.analysts.news_analyst",
        "tradingagents.agents.analysts.fundamentals_analyst",
        "tradingagents.agents.analysts.sentiment_analyst",
    ):
        importlib.import_module(mod)
```

Run: `pytest tests/backend/test_methodology.py -v`
Expected: PASS (all)

- [ ] **Step 8: 提交**

```bash
git add tradingagents/agents/analysts/ tests/backend/test_methodology.py
git commit -m "feat(agents): 4 个分析师 system prompt 拼接外置方法论"
```

---

### Task 3: PortfolioDecision 新增 conviction_score 字段

**Files:**
- Modify: `tradingagents/agents/schemas.py`(`PortfolioDecision` 类 + `render_pm_decision`)
- Test: `tests/backend/test_structured_agents.py`(**新建**;branch 3.1 上该文件不存在)

- [ ] **Step 1: 写失败测试**

Create `tests/backend/test_structured_agents.py` with:

```python
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
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/backend/test_structured_agents.py -k conviction -v`
Expected: FAIL — `TypeError`/`ValidationError` (unknown field `conviction_score`)

- [ ] **Step 3: 实现**

In `tradingagents/agents/schemas.py`, in class `PortfolioDecision`, add this field after the `rating` field (after line 185, before `executive_summary`):

```python
    conviction_score: Optional[int] = Field(
        default=None,
        description=(
            "Conviction in this rating on a 1-10 integer scale (1 = very low "
            "conviction, 10 = very high). Base it on how decisively the "
            "analysts' debate favored one side and the quality of the "
            "supporting evidence."
        ),
    )
```

In `render_pm_decision` (currently lines 232-261), add the conviction line right after the `**Rating**` line. Change the `parts` list head from:

```python
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
```

to:

```python
    parts = [
        f"**Rating**: {decision.rating.value}",
    ]
    if decision.conviction_score is not None:
        parts.append(f"**Conviction**: {decision.conviction_score}/10")
    parts += [
        "",
        f"**Executive Summary**: {decision.executive_summary}",
```

(Leave the rest of `render_pm_decision` unchanged.)

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `pytest tests/backend/test_structured_agents.py -v`
Expected: PASS (all, including pre-existing)

- [ ] **Step 5: 提交**

```bash
git add tradingagents/agents/schemas.py tests/backend/test_structured_agents.py
git commit -m "feat(schemas): PortfolioDecision 新增可选 conviction_score(1-10)"
```

---

### Task 4: capture 变体 + Portfolio Manager 输出结构对象

**Files:**
- Modify: `tradingagents/agents/utils/structured.py`(新增 `invoke_structured_or_freetext_capture`)
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Test: `tests/backend/test_structured_agents.py`(追加到 Task 3 新建的文件)

- [ ] **Step 1: 写失败测试**

Append to `tests/backend/test_structured_agents.py`:

```python
def test_capture_returns_markdown_and_parsed_object():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
    from tradingagents.agents.utils.structured import (
        invoke_structured_or_freetext_capture,
    )

    obj = PortfolioDecision(
        rating="Buy", executive_summary="s", investment_thesis="t",
        conviction_score=9,
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
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/backend/test_structured_agents.py -k capture -v`
Expected: FAIL — `ImportError: cannot import name 'invoke_structured_or_freetext_capture'`

- [ ] **Step 3: 实现 capture 变体并让旧函数复用它**

In `tradingagents/agents/utils/structured.py`, replace the body of `invoke_structured_or_freetext` (currently the whole function after its docstring) so the parsing logic lives in a new capture function and the old function delegates. Add `from typing import Tuple` is unnecessary (use lowercase tuple in return hint via `Optional[Any]`). Concretely, add this new function and rewrite the old one to delegate:

```python
def invoke_structured_or_freetext_capture(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> tuple[str, Optional[T]]:
    """Like invoke_structured_or_freetext but also returns the parsed object.

    Returns ``(markdown, parsed)``. ``parsed`` is the typed Pydantic
    instance when structured output succeeded, or ``None`` when the
    free-text fallback fired (so callers can decide whether to expose the
    structured fields downstream).
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                logger.warning(
                    "%s: structured-output returned None (model emitted no "
                    "tool-call); retrying once as free text",
                    agent_name,
                )
            else:
                return render(result), result
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content, None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Backward-compatible wrapper: returns only the rendered markdown."""
    markdown, _ = invoke_structured_or_freetext_capture(
        structured_llm, plain_llm, prompt, render, agent_name
    )
    return markdown
```

(Delete the old standalone implementation body of `invoke_structured_or_freetext`; keep the module docstring and `bind_structured` untouched. Trader and Research Manager keep calling `invoke_structured_or_freetext` unchanged.)

- [ ] **Step 4: Portfolio Manager 返回结构对象**

In `tradingagents/agents/managers/portfolio_manager.py`:
- Update the import (currently lines 22-25) to also import the capture variant:

```python
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_capture,
)
```

- Replace the `invoke_structured_or_freetext(...)` call (the block assigning `final_trade_decision`) with:

```python
        final_trade_decision, decision_obj = invoke_structured_or_freetext_capture(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )
```

- In the `return {...}` dict at the end of `portfolio_manager_node`, add the structured payload:

```python
        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "portfolio_decision": (
                decision_obj.model_dump() if decision_obj is not None else None
            ),
        }
```

- [ ] **Step 5: 运行,确认通过 + 无回归**

Run: `pytest tests/backend/test_structured_agents.py -v`
Expected: PASS (all)

- [ ] **Step 6: 提交**

```bash
git add tradingagents/agents/utils/structured.py tradingagents/agents/managers/portfolio_manager.py tests/backend/test_structured_agents.py
git commit -m "feat(pm): 保留解析出的 PortfolioDecision 至 final_state.portfolio_decision"
```

---

### Task 5: persist_run 生成 run_meta(免责声明 + 运行元数据)

**Files:**
- Modify: `backend/services/persistence.py`
- Test: `tests/backend/test_persistence.py`(追加)

- [ ] **Step 1: 写失败测试**

Append to `tests/backend/test_persistence.py`:

```python
def test_persist_run_writes_run_meta(tmp_path: Path, monkeypatch):
    from backend.services import pdf as pdf_service

    monkeypatch.setattr(pdf_service, "_render_pdf", lambda html: b"%PDF-1.4 x")
    persist_run(
        results_dir=tmp_path,
        ticker="META",
        trade_date="2026-02-02",
        final_state={"final_trade_decision": "Buy: x", "market_report": "m"},
        model="deepseek-v4-pro",
        provider="DeepSeek",
        token_stats={"total_tokens": 1234, "cost_usd": 0.05},
    )
    saved = json.loads(
        (tmp_path / "META" / "2026-02-02" / "final_state_report.json").read_text()
    )
    meta = saved["run_meta"]
    assert meta["model"] == "deepseek-v4-pro"
    assert meta["provider"] == "DeepSeek"
    assert meta["tokens"]["total_tokens"] == 1234
    assert meta["tokens"]["cost_usd"] == 0.05
    assert meta["generated_at"].endswith("Z")  # ISO8601 UTC
    assert "不构成任何投资" in meta["disclaimer"]
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/backend/test_persistence.py -k run_meta -v`
Expected: FAIL — `KeyError: 'run_meta'`

- [ ] **Step 3: 实现**

In `backend/services/persistence.py`, add after the existing imports:

```python
from datetime import datetime, timezone

DISCLAIMER = (
    "本报告由 AI 多智能体系统自动生成,仅供研究参考,不构成任何投资、"
    "法律或税务建议。所有结论须经合格专业人士复核后方可作为决策依据。"
)
```

In `persist_run`, right after the `serializable = {...}` line and the existing `if token_stats is not None:` block, insert the run_meta construction (before `json_path = ...`):

```python
    ts = token_stats or {}
    serializable["run_meta"] = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "model": model,
        "provider": provider,
        "tokens": {
            "total_tokens": ts.get("total_tokens"),
            "cost_usd": ts.get("cost_usd"),
        },
        "disclaimer": DISCLAIMER,
    }
```

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `pytest tests/backend/test_persistence.py -v`
Expected: PASS (all, including pre-existing idempotent/index tests)

- [ ] **Step 5: 提交**

```bash
git add backend/services/persistence.py tests/backend/test_persistence.py
git commit -m "feat(persistence): final_state 注入 run_meta(时间戳/模型/token/免责声明)"
```

---

### Task 6: PDF 决策表格化 + 合规页脚

**Files:**
- Modify: `backend/services/pdf.py`
- Test: `tests/backend/test_pdf_routes.py`(追加)

- [ ] **Step 1: 写失败测试**

Append to `tests/backend/test_pdf_routes.py`:

```python
def test_pdf_html_renders_decision_table_and_footer():
    from backend.services.pdf import _build_html

    final_state = {
        "market_report": "# M\nx",
        "final_trade_decision": "**Rating**: Buy",
        "portfolio_decision": {
            "rating": "Buy",
            "conviction_score": 8,
            "executive_summary": "建仓区间 250-255",
            "investment_thesis": "多头论据更强",
            "price_target": 300.0,
            "stop_loss": 240.0,
            "breakout_point": 260.0,
            "time_horizon": "1-3 个月",
            "outlook_30d": "区间震荡",
            "outlook_60d": "趋势向上",
            "outlook_90d": "突破确认加仓",
        },
        "run_meta": {
            "generated_at": "2026-02-02T03:04:05Z",
            "model": "deepseek-v4-pro",
            "provider": "DeepSeek",
            "tokens": {"total_tokens": 1234, "cost_usd": 0.05},
            "disclaimer": "本报告由 AI 多智能体系统自动生成,不构成任何投资建议。",
        },
    }
    html = _build_html(final_state, "TEST", "2026-02-02")
    assert "<table" in html
    assert "8/10" in html              # conviction rendered
    assert "建仓区间 250-255" in html   # executive summary
    assert "240" in html               # stop loss
    assert "本报告由 AI 多智能体系统自动生成" in html  # disclaimer footer
    assert "deepseek-v4-pro" in html   # run meta


def test_pdf_html_falls_back_to_markdown_when_no_structured_decision():
    from backend.services.pdf import _build_html

    html = _build_html(
        {"final_trade_decision": "**Rating**: Hold\n纯文本回退"},
        "TEST",
        "2026-02-02",
    )
    assert "纯文本回退" in html
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/backend/test_pdf_routes.py -k "decision_table or markdown_when_no" -v`
Expected: FAIL — `assert "<table" in html` (no structured table yet) / footer missing

- [ ] **Step 3: 实现决策表格 + 页脚**

In `backend/services/pdf.py`:

- Add CSS for footer/table to `_CSS` (append before the closing quote on the `_CSS` string, after the existing `th {...}` rule):

```python
    " .decision-table td:first-child { background:#f8fafc; font-weight:bold; width:30%; }"
    " .report-footer { margin-top:30px; padding-top:10px; border-top:1px solid #e2e8f0;"
    " font-size:8pt; color:#94a3b8; }"
```

- Add two helper functions above `_build_html`:

```python
_DECISION_ROWS = [
    ("rating", "评级"),
    ("conviction_score", "信心度"),
    ("price_target", "目标位"),
    ("stop_loss", "止损位"),
    ("breakout_point", "突破位"),
    ("time_horizon", "时间窗口"),
    ("outlook_30d", "30天展望"),
    ("outlook_60d", "60天展望"),
    ("outlook_90d", "90天展望"),
]


def _decision_table_html(decision: dict) -> str:
    rows = []
    for key, label in _DECISION_ROWS:
        val = decision.get(key)
        if val is None or val == "":
            continue
        cell = f"{val}/10" if key == "conviction_score" else val
        rows.append(
            f"<tr><td>{html.escape(label)}</td>"
            f"<td>{html.escape(str(cell))}</td></tr>"
        )
    table = f"<table class='decision-table'>{''.join(rows)}</table>" if rows else ""
    summary = decision.get("executive_summary") or ""
    thesis = decision.get("investment_thesis") or ""
    blocks = [table]
    if summary:
        blocks.append(
            f"<h3>核心决策摘要</h3>{markdown2.markdown(str(summary))}"
        )
    if thesis:
        blocks.append(f"<h3>投资论据</h3>{markdown2.markdown(str(thesis))}")
    return "\n".join(b for b in blocks if b)


def _footer_html(final_state: dict) -> str:
    meta = final_state.get("run_meta")
    if not isinstance(meta, dict):
        return ""
    tokens = meta.get("tokens") or {}
    line = (
        f"生成时间: {html.escape(str(meta.get('generated_at') or '-'))} | "
        f"模型: {html.escape(str(meta.get('model') or '-'))} | "
        f"供应商: {html.escape(str(meta.get('provider') or '-'))} | "
        f"Tokens: {html.escape(str(tokens.get('total_tokens') or '-'))} | "
        f"成本(USD): {html.escape(str(tokens.get('cost_usd') or '-'))}"
    )
    disclaimer = html.escape(str(meta.get("disclaimer") or ""))
    return f"<div class='report-footer'><p>{line}</p><p>{disclaimer}</p></div>"
```

- In `_build_html`, the final-decision section currently goes through the generic `_SECTIONS` loop via key `final_trade_decision`. Replace the prose `final_trade_decision` rendering with the structured table when available. After the `for section_title, keys in _SECTIONS:` loop completes (after the loop body, before `body = "\n".join(parts)`), insert:

```python
    decision = final_state.get("portfolio_decision")
    if isinstance(decision, dict):
        parts.append(
            "<h2>最终投资决策</h2>" + _decision_table_html(decision)
        )
```

And in the `_SECTIONS` constant (lines 22-27), remove the `("final_trade_decision", "最终投资决策")` entry from the "第四/五阶段" group so it is not double-rendered as prose. The group becomes:

```python
    ("第四/五阶段：风险管理与最终决策", [
        ("risk_debate_state.aggressive_history", "激进型分析师辩论"),
        ("risk_debate_state.conservative_history", "保守型分析师辩论"),
        ("risk_debate_state.neutral_history", "中立型分析师辩论"),
    ]),
```

To preserve the markdown fallback when `portfolio_decision` is absent (free-text runs / historical data), after the inserted structured block add:

```python
    elif final_state.get("final_trade_decision"):
        parts.append(
            "<h2>最终投资决策</h2>"
            + markdown2.markdown(
                str(final_state["final_trade_decision"]),
                extras=["tables", "fenced-code-blocks", "header-ids"],
            )
        )
```

- Finally, append the footer to `body`. Change `body = "\n".join(parts)` to:

```python
    body = "\n".join(parts) + _footer_html(final_state)
```

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `pytest tests/backend/test_pdf_routes.py -v`
Expected: PASS (all, including pre-existing 404/pdf-bytes tests)

- [ ] **Step 5: 提交**

```bash
git add backend/services/pdf.py tests/backend/test_pdf_routes.py
git commit -m "feat(pdf): 结构化决策表格化 + 合规页脚(回退保留 markdown)"
```

---

### Task 7: 前端 — 决策表格 + 元数据/免责声明

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/RunReportPage.tsx`
- Test: `frontend/src/pages/RunReportPage.test.tsx`(追加)

- [ ] **Step 1: 写失败测试**

Append to `frontend/src/pages/RunReportPage.test.tsx` a new test (mirroring the existing mock pattern at the top of the file; the existing test mocks `getRunReport` via `getRunReport`/fetch — match whatever the existing test uses; here we mock the same `getRunReport` module function):

```tsx
it("renders structured decision table and compliance footer", async () => {
  const { getRunReport } = await import("../api/client");
  vi.spyOn({ getRunReport }, "getRunReport");
  vi.mock("../api/client", async (orig) => {
    const mod = (await orig()) as Record<string, unknown>;
    return {
      ...mod,
      getRunReport: vi.fn().mockResolvedValue({
        ticker: "AAPL",
        trade_date: "2026-01-02",
        final_state: {
          market_report: "# M\nx",
          portfolio_decision: {
            rating: "Buy",
            conviction_score: 8,
            executive_summary: "建仓 250-255",
            investment_thesis: "多头更强",
            stop_loss: 240,
            time_horizon: "1-3 个月",
          },
          run_meta: {
            generated_at: "2026-01-02T03:04:05Z",
            model: "deepseek-v4-pro",
            provider: "DeepSeek",
            tokens: { total_tokens: 1234, cost_usd: 0.05 },
            disclaimer: "本报告由 AI 多智能体系统自动生成,不构成任何投资建议。",
          },
        },
      }),
    };
  });
  renderPage("/history/AAPL/2026-01-02");
  await waitFor(() =>
    expect(screen.getByText(/建仓 250-255/)).toBeInTheDocument(),
  );
  expect(screen.getByText(/8\/10/)).toBeInTheDocument();
  expect(screen.getByText(/不构成任何投资建议/)).toBeInTheDocument();
  expect(screen.getByText(/deepseek-v4-pro/)).toBeInTheDocument();
});
```

> Implementer note: keep the existing test's mocking style. If the existing test mocks `getRunReport` differently (e.g. via global `fetch`), replicate that exact approach and only swap in the `final_state` payload above. The behavioral assertions (table text, `8/10`, disclaimer, model) are what matter.

- [ ] **Step 2: 运行,确认失败**

Run: `cd frontend && npx vitest run src/pages/RunReportPage.test.tsx`
Expected: FAIL — disclaimer / `8/10` not found

- [ ] **Step 3: 类型定义**

In `frontend/src/api/types.ts`, add after `RunReportResponse` (line 65):

```typescript
export interface PortfolioDecision {
  rating: string;
  conviction_score?: number | null;
  executive_summary?: string;
  investment_thesis?: string;
  price_target?: number | null;
  stop_loss?: number | null;
  breakout_point?: number | null;
  time_horizon?: string | null;
  outlook_30d?: string | null;
  outlook_60d?: string | null;
  outlook_90d?: string | null;
}

export interface RunMeta {
  generated_at: string;
  model: string | null;
  provider: string | null;
  tokens: { total_tokens: number | null; cost_usd: number | null };
  disclaimer: string;
}
```

- [ ] **Step 4: 渲染决策表格 + 元数据/免责声明**

In `frontend/src/pages/RunReportPage.tsx`:

- Add imports at top: `import type { PortfolioDecision, RunMeta } from "../api/types";`
- Remove `final_trade_decision` from the last `REPORT_GROUPS` entry (line 56) so it is not double-rendered as prose; the group keeps only the three risk-debate sections.
- Add these helpers above the component (after `buildGroups`):

```tsx
const DECISION_ROWS: [keyof PortfolioDecision, string][] = [
  ["rating", "评级"],
  ["conviction_score", "信心度"],
  ["price_target", "目标位"],
  ["stop_loss", "止损位"],
  ["breakout_point", "突破位"],
  ["time_horizon", "时间窗口"],
  ["outlook_30d", "30天展望"],
  ["outlook_60d", "60天展望"],
  ["outlook_90d", "90天展望"],
];

function DecisionCard({ d }: { d: PortfolioDecision }) {
  return (
    <section className="card col">
      <h3>最终投资决策</h3>
      <table className="decision-table">
        <tbody>
          {DECISION_ROWS.map(([k, label]) => {
            const v = d[k];
            if (v === null || v === undefined || v === "") return null;
            const text = k === "conviction_score" ? `${v}/10` : String(v);
            return (
              <tr key={k}>
                <td style={{ fontWeight: 600, width: "30%" }}>{label}</td>
                <td>{text}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {d.executive_summary && (
        <article>
          <h4>核心决策摘要</h4>
          <Markdown>{d.executive_summary}</Markdown>
        </article>
      )}
      {d.investment_thesis && (
        <article>
          <h4>投资论据</h4>
          <Markdown>{d.investment_thesis}</Markdown>
        </article>
      )}
    </section>
  );
}

function ComplianceFooter({ meta }: { meta: RunMeta }) {
  return (
    <section className="card col" style={{ fontSize: "0.8rem", color: "var(--muted, #94a3b8)" }}>
      <div>
        生成时间: {meta.generated_at} | 模型: {meta.model ?? "-"} | 供应商:{" "}
        {meta.provider ?? "-"} | Tokens: {meta.tokens?.total_tokens ?? "-"} | 成本(USD):{" "}
        {meta.tokens?.cost_usd ?? "-"}
      </div>
      <div>{meta.disclaimer}</div>
    </section>
  );
}
```

- In the component body, after `const groups = useMemo(...)`, derive the structured pieces:

```tsx
  const decision = (finalState?.portfolio_decision ?? null) as PortfolioDecision | null;
  const runMeta = (finalState?.run_meta ?? null) as RunMeta | null;
  const fallbackDecision =
    !decision && finalState && typeof finalState.final_trade_decision === "string"
      ? (finalState.final_trade_decision as string)
      : "";
```

- In the JSX, after the `groups.map(...)` block and before the closing `</div>`, render:

```tsx
      {!loading && !error && decision && <DecisionCard d={decision} />}
      {!loading && !error && !decision && fallbackDecision && (
        <section className="card col">
          <h3>最终投资决策</h3>
          <Markdown>{fallbackDecision}</Markdown>
        </section>
      )}
      {!loading && !error && runMeta && <ComplianceFooter meta={runMeta} />}
```

- [ ] **Step 5: 运行,确认通过 + 无回归**

Run: `cd frontend && npx vitest run src/pages/RunReportPage.test.tsx`
Expected: PASS (new test + the pre-existing "loads and renders" test)

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/types.ts frontend/src/pages/RunReportPage.tsx frontend/src/pages/RunReportPage.test.tsx
git commit -m "feat(frontend): 结构化决策表格 + 合规元数据/免责声明展示"
```

---

### Task 8: 全量回归 + 收尾

**Files:** 无新增(验证)

- [ ] **Step 1: 后端全量测试**

Run: `pytest tests/backend -q`
Expected: 全部通过,无回归。

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部通过,无回归。

- [ ] **Step 3: 手动冒烟(可选,UI 验证)**

启动后端 + 前端(`./dev.sh` 或既有方式),跑一次分析,确认:
- 报告页底部出现免责声明与运行元数据条;
- 结构化运行显示决策表格(含 信心度 N/10);
- 旧的历史 JSON(无 `portfolio_decision`/`run_meta`)仍能打开,决策回退为 markdown,无报错。

- [ ] **Step 4: 终检提交(若有遗留改动)**

```bash
git add -A
git commit -m "chore: P0 升级回归验证收尾"
```

---

## Self-Review

**Spec coverage:**
- 组件 1(方法论外置)→ Task 1 + Task 2 ✅
- 组件 2(结构化 + conviction + 表格化)→ Task 3(schema)+ Task 4(对象流转)+ Task 6(PDF 表格)+ Task 7(前端表格)✅
- 组件 3(合规 footer + 元数据)→ Task 5(JSON/run_meta,SQLite 已有 created_at)+ Task 6(PDF 页脚)+ Task 7(前端展示)✅
- 测试章节(test_methodology / schemas / persistence / pdf / RunReportPage)→ 覆盖于各 Task + Task 8 全量回归 ✅
- 范围外项(分析师级评分/连接器/隔离/回测)→ 计划未包含,符合 YAGNI ✅

**Placeholder scan:** 无 TBD/TODO;每个代码步骤含完整代码。sentiment_analyst Step 6 与前端 Step 1 含"实现者注记",因二者依赖文件中既有表达式/既有 mock 风格——已给出明确的不变量与行为断言,非占位。

**Type consistency:** `get_methodology(key)`、`invoke_structured_or_freetext_capture(...) -> (str, Optional[T])`、`PortfolioDecision.conviction_score`、`final_state["portfolio_decision"]`(dict via `model_dump()`)、`run_meta`(generated_at/model/provider/tokens{total_tokens,cost_usd}/disclaimer)、前端 `PortfolioDecision`/`RunMeta` 接口——跨 Task 命名一致。`_DECISION_ROWS`(后端)与 `DECISION_ROWS`(前端)字段键一致。
