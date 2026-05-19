# 设计:trader/PM 结构化自检 + trader 计划对齐(Phase C 首批)

**日期:** 2026-05-19
**状态:** 已确认,待实现计划
**前序:** P0、Phase A(8 决策类 agent 方法论)、辩论轮次显示、fundamentals/sentiment 收紧均已完成。

## 背景

对 TQQQ(2026-05-19,改后)真实运行核对 Phase A 8 个决策类 agent:6 个自由文本/辩论类 agent(多头/空头研究员、激进/保守/中立辩论、研究经理 rationale)均稳定输出 `【自检】` 块,达 Tier 3;但 **trader 与 portfolio_manager 未输出 `【自检】` 块**。

根因:这两个 agent 是结构化输出 agent(走 `TraderProposal` / `PortfolioDecision` Pydantic schema → `render_*` 固定渲染),Phase A 方法论写的"在 reasoning/investment_thesis **文本末尾**追加【自检】"被结构化约束压过,未落地。附带实质问题:trader 输出 `Action: Sell`,但其 reasoning 文末写"…故取 **Underweight** 而非 Sell"——行动字段与论据自相矛盾(研究经理裁定 Underweight),正是 trader.md 想用自检拦截的错误,因自检未生成而未被拦截。

本批属 Phase C(决策类 agent 结构化分步自验证)的**首批**,只解决"结构化终检字段 + trader 计划对齐",Phase C 余下(分步中间确认等)另议。

## 范围

仅:`tradingagents/agents/schemas.py`(2 schema + 2 render 函数)、`tradingagents/methodology/trader.md`、`tradingagents/methodology/portfolio_manager.md`、相关测试。**不动** PDF、前端、types.ts、其它方法论文件、research_manager 及自由文本类 agent。

## 设计

### 1. schemas.py 字段新增(必填)

**`TraderProposal`** 新增两个必填 `str` 字段:
- `plan_alignment`:Field 描述要求 LLM 说明本 `action` 如何由研究经理投资计划评级(Buy/Overweight/Hold/Underweight/Sell)映射而来;若方向与该评级背离,必须给出明确理由。
- `self_check`:Field 描述列明 trader.md 的 4 条自检项,要求逐条以 `☑ …` 形式填写并附简短依据(含"行动方向与研究计划评级一致或已说明分歧理由"一条)。

**`PortfolioDecision`** 新增一个必填 `str` 字段:
- `self_check`:Field 描述列明 portfolio_manager.md 的 4 条自检项,逐条 `☑` + 简短依据。

**取舍说明**:设为必填以最大化 schema 层强制。代价:弱模型漏填 → Pydantic 校验失败 → 走既有 `invoke_structured_or_freetext(_capture)` 的 free-text 优雅回退(与现状一致);并且既有 `tests/backend/test_structured_agents.py` 中构造 `TraderProposal(...)`/`PortfolioDecision(...)` 的用例需补这两个新必填字段(已知、受控的连带改动)。`conviction_score` 当年用 Optional,但本特性目的就是强制自检,故选必填。

### 2. render_* 渲染

- `render_trader_proposal`:在现有字段之后、保留的尾行 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`(向后兼容,greppable,不动)**之前**,插入:
  - `**计划对齐**: {plan_alignment}`
  - `**【自检】**\n{self_check}`
- `render_pm_decision`:在现有 outlook 字段之后追加 `**【自检】**\n{self_check}`。
- 渲染后的 markdown 自动随 `trader_investment_plan` / `final_trade_decision` 进入 memory log / sqlite / PDF-markdown 回退路径——无需改 PDF/前端。

### 3. 方法论对齐(仅 trader.md + portfolio_manager.md)

二者现有 `## 输出末尾自检` 节当前指示"在 reasoning/investment_thesis 文本末尾追加【自检】"(失效根因)。改为指示:**填写结构化 `self_check` 字段**(trader 另填 `plan_alignment` 字段),逐条自检项内容保持不变。仍须保留 `【自检】` 字样(Phase A 既有测试 `test_phase_a_methodology_keys_present_and_nonempty` 断言该串在这两文件中存在)。`researcher.md`/`risk_debate.md`/`research_manager.md`/4 个分析师方法论文件**一律不动**。

### 4. trader Action/评级一致性

不硬编码 PortfolioRating→TraderAction 映射(保留 trader 判断空间)。通过新 `plan_alignment` 必填字段强制 trader 显式陈述"本 Action 如何由研究计划评级映射、背离理由",并由 `self_check` 第 1 条断言一致性。可拦截上次 `Action=Sell` 而文末写"故取 Underweight 而非 Sell"的自相矛盾。

## 测试

- `tests/backend/test_structured_agents.py`:
  - 更新既有构造 `TraderProposal(...)` / `PortfolioDecision(...)` 的用例,补必填新字段(否则 ValidationError)。
  - 新增断言:`TraderProposal` 含必填 `plan_alignment` 与 `self_check`;`PortfolioDecision` 含必填 `self_check`(缺失即 ValidationError)。
  - 新增断言:`render_trader_proposal(...)` 输出含 `**计划对齐**`、`**【自检】**`,且尾行 `FINAL TRANSACTION PROPOSAL` 仍存在;`render_pm_decision(...)` 输出含 `**【自检】**`。
- `tests/backend/test_methodology.py`:`get_methodology("trader")`/`get_methodology("portfolio_manager")` 仍含 `【自检】`;新增断言其提及结构化字段名(`self_check`,trader 另含 `plan_alignment`)。Phase A 既有断言保持通过。
- 后端全量 `pytest tests/backend` 无回归(重点关注 capture 路径 `test_structured_agents.py`、`test_persistence.py`、PDF-markdown 相关)。
- 真实 LLM 是否按填——靠后续 TQQQ 类冒烟验证,不在单测验收内。

## 验收标准

- `TraderProposal` 有必填 `plan_alignment`、`self_check`;`PortfolioDecision` 有必填 `self_check`;缺失触发 ValidationError。
- `render_trader_proposal` 输出在尾行 `FINAL TRANSACTION PROPOSAL` 之前含 `**计划对齐**` 与 `**【自检】**` 块;`render_pm_decision` 末尾含 `**【自检】**` 块。
- `trader.md`、`portfolio_manager.md` 的自检节改为指向结构化字段,仍含 `【自检】`;其它方法论文件零改动。
- 既有 schema 构造测试已补新字段;新增/修改测试全部通过;后端全量无回归。

## 范围外(YAGNI)

- PDF 结构化表格、前端决策卡、`types.ts`(用户明确选择不动)。
- research_manager 及自由文本类 6 个 agent(自由文本自检已验证生效)。
- 硬编码评级→动作映射。
- Phase C 余下部分(分步中间确认、跨阶段一致性校验等)。
- 任何图拓扑 / streaming / 前端改动。
