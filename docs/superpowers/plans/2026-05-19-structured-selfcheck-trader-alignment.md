# trader/PM 结构化自检 + trader 计划对齐 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `TraderProposal` 加必填 `plan_alignment` + `self_check`、给 `PortfolioDecision` 加必填 `self_check`,在 `render_*` 渲染出来,并把 trader.md / portfolio_manager.md 的自检节改为指向结构化字段,使 trader/PM 的【自检】真正落地、并拦截 trader Action 与研究计划评级的矛盾。

**Architecture:** 改 `tradingagents/agents/schemas.py`(2 schema + 2 render 函数)与 2 个方法论 .md;复用既有结构化 capture 路径(零图拓扑/前端/PDF 改动)。新字段必填 → 既有 `test_structured_agents.py` 中 6 处 `PortfolioDecision(...)` 构造需同批补字段。

**Tech Stack:** Python / Pydantic / pytest;Markdown 方法论。

**参考规格:** `docs/superpowers/specs/2026-05-19-structured-selfcheck-trader-alignment-design.md`

**环境注意:** `rtk` 代理过滤 pytest 输出;pytest 必须经 `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest <args> -p no:cacheprovider"`。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**已核对基线(真实代码):**
- `tradingagents/agents/schemas.py`:`TraderProposal`(行 109-138,字段 action/reasoning/entry_price/stop_loss/position_sizing);`render_trader_proposal`(行 141-163,尾部 `parts.extend(["", f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**"])` 然后 `return "\n".join(parts)`);`PortfolioDecision`(行 171-240,末字段 outlook_90d);`render_pm_decision`(行 243-276,末尾 `if decision.outlook_90d: parts.extend(["", f"**90-Day Outlook**: {decision.outlook_90d}"])` 然后 `return "\n".join(parts)`)。`Field` 与 `Optional` 已在文件顶部导入。
- `tests/backend/test_structured_agents.py`:6 处 `PortfolioDecision(...)` 构造(行 4、11、24、30、45、57)均无 `self_check`;无 `TraderProposal(...)` 构造。
- `tradingagents/methodology/trader.md` 末节为 `## 输出末尾自检(必须在 reasoning 文本末尾逐项标注)` + `【自检】` + 4 条 ☑;`portfolio_manager.md` 末节为 `## 输出末尾自检(必须在 investment_thesis 文本末尾逐项标注)` + `【自检】` + 4 条 ☑。
- `tests/backend/test_methodology.py` 顶部已 `from tradingagents.agents.utils.agent_utils import get_methodology`;Phase A 测试 `test_phase_a_methodology_keys_present_and_nonempty` 断言 `引用即纪律` 与 `【自检】` 在 trader/portfolio_manager 方法论中存在(本计划保持二者仍存在)。

---

### Task 1: schemas.py 新增结构化字段 + render + 修既有测试构造

**Files:**
- Modify: `tradingagents/agents/schemas.py`
- Test: `tests/backend/test_structured_agents.py`(更新既有 6 处构造 + 追加新测试)

- [ ] **Step 1: 更新既有构造 + 追加失败测试**

(a) 在 `tests/backend/test_structured_agents.py` 中,给所有 6 处 `PortfolioDecision(...)` 构造补必填 `self_check`。逐处精确修改:

行 4-8:
```python
    d = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
        self_check="sc",
    )
```
行 11-16:
```python
    d2 = PortfolioDecision(
        rating="Buy",
        executive_summary="s",
        investment_thesis="t",
        conviction_score=8,
        self_check="sc",
    )
```
行 24:
```python
        PortfolioDecision(rating="Hold", executive_summary="s", investment_thesis="t", self_check="sc")
```
行 30-33:
```python
        PortfolioDecision(
            rating="Buy", executive_summary="s", investment_thesis="t",
            conviction_score=7, self_check="sc",
        )
```
行 45-48:
```python
            PortfolioDecision(
                rating="Buy", executive_summary="s", investment_thesis="t",
                conviction_score=bad, self_check="sc",
            )
```
行 57-60:
```python
    obj = PortfolioDecision(
        rating="Buy", executive_summary="s", investment_thesis="t",
        conviction_score=9, self_check="sc",
    )
```

(b) 在 `tests/backend/test_structured_agents.py` 末尾追加新测试:
```python


def test_trader_proposal_requires_plan_alignment_and_self_check():
    import pytest
    from pydantic import ValidationError
    from tradingagents.agents.schemas import TraderProposal

    # both new fields required
    with pytest.raises(ValidationError):
        TraderProposal(action="Sell", reasoning="r")

    tp = TraderProposal(
        action="Sell",
        reasoning="r",
        plan_alignment="研究计划评级 Underweight → 减仓,本提案方向一致",
        self_check="☑ 行动方向与研究计划评级一致\n☑ 无未溯源数字\n☑ 已给出入场/止损\n☑ 已覆盖关键风险",
    )
    assert tp.plan_alignment
    assert tp.self_check


def test_render_trader_proposal_includes_alignment_and_selfcheck():
    from tradingagents.agents.schemas import TraderProposal, render_trader_proposal

    md = render_trader_proposal(
        TraderProposal(
            action="Sell",
            reasoning="r",
            plan_alignment="评级 Underweight → 减仓,方向一致",
            self_check="☑ 行动方向与研究计划评级一致",
        )
    )
    assert "**计划对齐**: 评级 Underweight → 减仓,方向一致" in md
    assert "**【自检】**" in md
    assert "☑ 行动方向与研究计划评级一致" in md
    # backward-compatible trailing line preserved AFTER the self-check block
    assert md.rstrip().endswith("FINAL TRANSACTION PROPOSAL: **SELL**")


def test_portfolio_decision_requires_self_check():
    import pytest
    from pydantic import ValidationError
    from tradingagents.agents.schemas import PortfolioDecision

    with pytest.raises(ValidationError):
        PortfolioDecision(rating="Buy", executive_summary="s", investment_thesis="t")

    d = PortfolioDecision(
        rating="Buy", executive_summary="s", investment_thesis="t",
        self_check="☑ 结论锚定风险辩论具体证据",
    )
    assert d.self_check


def test_render_pm_decision_includes_self_check():
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision

    md = render_pm_decision(
        PortfolioDecision(
            rating="Hold", executive_summary="s", investment_thesis="t",
            self_check="☑ 结论锚定风险辩论具体证据\n☑ 无未溯源数字",
        )
    )
    assert "**【自检】**" in md
    assert "☑ 结论锚定风险辩论具体证据" in md
    assert "**Rating**: Hold" in md  # back-compat header preserved
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_structured_agents.py -v -p no:cacheprovider"`
Expected: 新测试 FAIL(TraderProposal 无 plan_alignment/self_check 字段;render 不含新块;PortfolioDecision.self_check 不存在)。既有测试此时也会因构造未补字段而……(注意:Step 1(a) 已补 self_check,但此时 schema 尚无 self_check 字段 → 既有构造传未知 kwarg。Pydantic v2 默认忽略未知字段不报错,故既有测试仍 PASS;若该项目 model_config 设了 `extra="forbid"`,既有测试会暂时报错——此为预期的红灯,Step 4 实现后转绿)。

- [ ] **Step 3: 实现 schema + render**

在 `tradingagents/agents/schemas.py`:

(a) `TraderProposal` 类:在 `reasoning` 字段之后、`entry_price` 字段之前,插入两个必填字段:
```python
    plan_alignment: str = Field(
        description=(
            "State how this action maps from the Research Manager's investment "
            "plan rating (Buy / Overweight / Hold / Underweight / Sell). If the "
            "action's direction diverges from that rating, give an explicit "
            "justification for the divergence."
        ),
    )
    self_check: str = Field(
        description=(
            "A self-check block the trader MUST fill — one line per item, each "
            "starting with ☑ followed by a brief justification:\n"
            "☑ 行动方向与研究计划评级一致(或已说明分歧理由)\n"
            "☑ 无未溯源数字\n"
            "☑ 已给出明确入场/止损参考\n"
            "☑ 已覆盖分析师报告中的关键风险"
        ),
    )
```

(b) `render_trader_proposal`:在 `if proposal.position_sizing: ...` 之后、现有 `parts.extend(["", f"FINAL TRANSACTION PROPOSAL: ...])` 之前,插入两行 extend。即把:
```python
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
```
改为:
```python
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend(["", f"**计划对齐**: {proposal.plan_alignment}"])
    parts.extend(["", "**【自检】**", proposal.self_check])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
```

(c) `PortfolioDecision` 类:在 `investment_thesis` 字段之后、`price_target` 字段之前,插入必填字段:
```python
    self_check: str = Field(
        description=(
            "A self-check block the Portfolio Manager MUST fill — one line per "
            "item, each starting with ☑ followed by a brief justification:\n"
            "☑ 结论锚定风险辩论具体证据\n"
            "☑ 无未溯源数字\n"
            "☑ 已按 has_position 个性化(建仓区间或加/减/保持)\n"
            "☑ 止损与展望与评级一致;已纳入历史教训(若提供)"
        ),
    )
```

(d) `render_pm_decision`:在末尾 `if decision.outlook_90d: ...` 之后、`return "\n".join(parts)` 之前,插入一行 extend。即把:
```python
    if decision.outlook_90d:
        parts.extend(["", f"**90-Day Outlook**: {decision.outlook_90d}"])
    return "\n".join(parts)
```
改为:
```python
    if decision.outlook_90d:
        parts.extend(["", f"**90-Day Outlook**: {decision.outlook_90d}"])
    parts.extend(["", "**【自检】**", decision.self_check])
    return "\n".join(parts)
```

不改其它字段/逻辑(conviction_score、outlooks、ResearchPlan 等保持原样)。

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_structured_agents.py -v -p no:cacheprovider"`
Expected: 全部 PASS(既有 conviction/capture 测试 + 4 个新测试)。
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全绿、0 失败。重点确认 `test_persistence.py`(PM 渲染进 final_state→json/pdf-markdown)与 capture 路径不回归;若某测试因 render 多出【自检】块而断言整段精确文本失败,属本改动引入,需把该断言改为子串/锚点断言(报告所改与理由);若是 freetext 回退路径(parsed=None)不受影响。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/agents/schemas.py tests/backend/test_structured_agents.py
git commit -m "feat(schemas): TraderProposal+PortfolioDecision 增结构化自检/计划对齐字段并渲染"
```

---

### Task 2: 方法论对齐 trader.md / portfolio_manager.md

**Files:**
- Modify: `tradingagents/methodology/trader.md`
- Modify: `tradingagents/methodology/portfolio_manager.md`
- Test: `tests/backend/test_methodology.py`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `tests/backend/test_methodology.py` 末尾追加(`get_methodology` 已在文件顶部导入,复用):

```python


def test_trader_pm_methodology_reference_structured_selfcheck():
    t = get_methodology("trader")
    assert "self_check" in t
    assert "plan_alignment" in t
    assert "【自检】" in t  # Phase A invariant kept
    p = get_methodology("portfolio_manager")
    assert "self_check" in p
    assert "【自检】" in p
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py::test_trader_pm_methodology_reference_structured_selfcheck -v -p no:cacheprovider"`
Expected: FAIL(当前两文件不含 `self_check`/`plan_alignment`)。

- [ ] **Step 3: 重写两文件的自检节**

`tradingagents/methodology/trader.md`:把当前末节
```
## 输出末尾自检(必须在 reasoning 文本末尾逐项标注)
【自检】
☑ 行动方向与研究计划评级一致(或已说明分歧理由)
☑ 无未溯源数字
☑ 已给出明确入场/止损参考
☑ 已覆盖分析师报告中的关键风险
```
整节替换为:
```
## 结构化自检(填入 schema 字段,非自由文本)
通过结构化输出填写以下字段,不要把这些堆叠到 reasoning 文本末尾:
- `plan_alignment`:说明本 action 如何由研究经理投资计划评级(Buy/Overweight/Hold/Underweight/Sell)映射而来;方向背离须给明确理由。
- `self_check`:逐条以 ☑ 填写并附简短依据:
  【自检】
  ☑ 行动方向与研究计划评级一致(或已说明分歧理由)
  ☑ 无未溯源数字
  ☑ 已给出明确入场/止损参考
  ☑ 已覆盖分析师报告中的关键风险
```

`tradingagents/methodology/portfolio_manager.md`:把当前末节
```
## 输出末尾自检(必须在 investment_thesis 文本末尾逐项标注)
【自检】
☑ 结论锚定风险辩论具体证据
☑ 无未溯源数字
☑ 已按 has_position 个性化(建仓区间或加/减/保持)
☑ 止损与展望与评级一致;已纳入历史教训(若提供)
```
整节替换为:
```
## 结构化自检(填入 schema 字段,非自由文本)
通过结构化输出填写 `self_check` 字段,不要把这些堆叠到 investment_thesis 文本末尾;逐条以 ☑ 填写并附简短依据:
【自检】
☑ 结论锚定风险辩论具体证据
☑ 无未溯源数字
☑ 已按 has_position 个性化(建仓区间或加/减/保持)
☑ 止损与展望与评级一致;已纳入历史教训(若提供)
```

两文件其它节(证据来源优先级 / 引用即纪律 / 常见错误)**一字不改**;保持文件末尾单换行。

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py -v -p no:cacheprovider"`
Expected: 全 PASS——新测试通过;Phase A `test_phase_a_methodology_keys_present_and_nonempty`(断言 `引用即纪律`+`【自检】` 在 trader/portfolio_manager 中)仍通过(引用即纪律节未动、【自检】 仍在);P0/Phase A/fundamentals/sentiment 既有断言不回归。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/methodology/trader.md tradingagents/methodology/portfolio_manager.md tests/backend/test_methodology.py
git commit -m "feat(methodology): trader/portfolio_manager 自检节改指向结构化字段"
```

---

### Task 3: 全量回归 + 收尾

**Files:** 无新增(验证)

- [ ] **Step 1: 后端全量**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,0 失败。

- [ ] **Step 2: 范围核验**

Run: `git diff --name-only HEAD~2..HEAD | sort -u`
Expected: 仅 `tradingagents/agents/schemas.py`、`tradingagents/methodology/trader.md`、`tradingagents/methodology/portfolio_manager.md`、`tests/backend/test_structured_agents.py`、`tests/backend/test_methodology.py`。无 PDF / 前端 / types.ts / 其它方法论 / 图拓扑改动。

- [ ] **Step 3: 手动冒烟(可选,非验收门槛)**

跑一次真实分析(如 TQQQ),核对 `trader_investment_plan` 含 `**计划对齐**` 与 `**【自检】**` 块且行动与研究计划评级一致(或显式说明分歧);`final_trade_decision` 末尾含 `**【自检】**` 块。单测只覆盖 schema/render/方法论文本正确性,不替代真实 LLM 行为验证。

- [ ] **Step 4: 收尾(如有遗留)**

```bash
git status --short
```
无遗留即完成;有则补一次提交。

---

## Self-Review

**Spec 覆盖:**
- TraderProposal 必填 `plan_alignment`+`self_check`、PortfolioDecision 必填 `self_check` → Task 1 Step 3(a)(c) + Step 1 新测试断言 ValidationError ✅
- render_trader_proposal 在 FINAL 行前插入 `**计划对齐**`+`**【自检】**`、render_pm_decision 末尾追加 `**【自检】**` → Task 1 Step 3(b)(d) + render 断言(含尾行仍在)✅
- 既有 6 处 PortfolioDecision 构造补必填字段 → Task 1 Step 1(a) 逐处给出 ✅
- 方法论仅改 trader.md/portfolio_manager.md 自检节、保留【自检】与引用即纪律、其它方法论不动 → Task 2 ✅
- trader Action/评级一致性靠 plan_alignment + self_check 第 1 条 → Task 1 字段 Field 描述 + Task 2 方法论 ✅
- 测试(schema 必填/render/方法论 + 全量无回归)→ Task 1/2/3 ✅
- 范围外(PDF/前端/types.ts/research_manager/自由文本 agent/硬映射)→ 计划未含;Task 3 Step 2 显式核验 ✅

**Placeholder 扫描:** 无 TBD/TODO;每处给出完整代码与精确 old→new;6 处构造逐处列出;两方法论整节替换文本逐字给出。

**类型/命名一致:** 字段名 `plan_alignment`/`self_check` 全程一致;render 输出标记 `**计划对齐**`/`**【自检】**` 与测试断言逐字一致;`FINAL TRANSACTION PROPOSAL: **SELL**` 尾行保留且断言其在自检块之后;方法论断言串 `self_check`/`plan_alignment`/`【自检】` 与 Task 2 写入文本一致;`get_methodology` key `"trader"`/`"portfolio_manager"` 与既有一致。
