# fundamentals/sentiment 纪律收紧 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `fundamentals.md` 纪律收紧到 market.md 标杆水准(实值优先 + 估算必标 + 期间强制 + 固定列汇总表 + 自检块),并给 `sentiment.md` 补一个可审计【自检】块。

**Architecture:** 纯 .md 改动,复用 P0 `get_methodology()` 加载器(零代码改动)。`fundamentals.md` 整文件重写(内容多,整写比多处 Edit 更稳),`sentiment.md` 末尾追加一节;`tests/backend/test_methodology.py` 增断言。news.md 不改。

**Tech Stack:** Markdown 方法论文件 / pytest。

**参考规格:** `docs/superpowers/specs/2026-05-19-fundamentals-sentiment-discipline-tightening-design.md`

**环境注意:** `rtk` 代理过滤 pytest 输出;pytest 必须经 `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest <args> -p no:cacheprovider"`。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**已核对的当前文件内容(基线):**
- `tradingagents/methodology/sentiment.md` 当前为 23 行,结构:`# 舆情情绪分析方法论` / `## 数据源优先级与可信度` / `## 情绪量化纪律` / `## QC 清单` / `## 常见错误`,最后一行是 `- 忽略数据源时效与样本偏差。`
- `tradingagents/methodology/fundamentals.md` 当前结构:`# 基本面分析方法论` / `## 数据源优先级` / `## 指标口径纪律` / `## QC 清单` / `## 常见错误`(P0 原版,无汇总表/自检块/实值优先规则)。
- `tests/backend/test_methodology.py` 顶部已 `from tradingagents.agents.utils.agent_utils import get_methodology`(P0 起);文末已有 P0/Phase A 各测试。

---

### Task 1: 重写 fundamentals.md + 加断言

**Files:**
- Modify(整文件覆盖写): `tradingagents/methodology/fundamentals.md`
- Test: `tests/backend/test_methodology.py`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `tests/backend/test_methodology.py` 末尾追加(`get_methodology` 已在文件顶部导入,复用,勿重复 import):

```python


def test_fundamentals_methodology_tightened():
    text = get_methodology("fundamentals")
    assert "实值优先" in text
    assert "估算·非工具直接读取" in text
    assert "指标 | 数值 | 期间 | 来源(工具/报表) | 实值或估算" in text
    assert "【自检】" in text
    assert "期间强制" in text
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py::test_fundamentals_methodology_tightened -v -p no:cacheprovider"`
Expected: FAIL（当前 fundamentals.md 不含这些标识)。

- [ ] **Step 3: 整文件覆盖写 `tradingagents/methodology/fundamentals.md`** —— 用 Write 工具写入 EXACTLY 以下完整内容(末尾保留一个换行):

```
# 基本面分析方法论

## 数据源优先级
1. `get_fundamentals` 公司概览。
2. 三大报表:`get_income_statement` / `get_balance_sheet` / `get_cashflow`。
3. `get_insider_transactions` 内部人交易作为辅助信号。

## 指标口径纪律
- 估值类(P/E、P/B、EV/EBITDA)、盈利质量(ROE、ROIC、毛/净利率)、偿债与现金流(负债率、自由现金流)分组评估,不可只看单一指标。
- 趋势优先于快照:尽量给多期变化而非单点值。
- 每个财务结论标注其来源报表与期间。
- **实值优先(硬规则):** ETF / 公司层面可取实值的指标(总净资产/AUM、费用率、远期 P/E、股息率、前十持仓及权重等)必须给出 `get_fundamentals` 返回的具体数值 + 数据截止日;严禁用估算区间(如 `~24x–27x`)替代本可取到的实值。
- **估算必标(硬规则):** 指数底层加权派生量(加权 ROE、加权毛/净利率等)在工具无法直接取时允许估算,但必须显式标注「估算·非工具直接读取」并写明推算依据;严禁给估算贴 `get_xxx` 来源标签伪装成实值。
- **期间强制(硬规则):** 每个数据点必须带期间或数据截止日(如 `(2026-05-18)` / `FY2025` / `2026Q1`);无期间的数字一律视为未溯源,须标「未溯源」或补全期间。

## 强制输出汇总表
报告结尾必须包含一张汇总表,列固定为:`指标 | 数值 | 期间 | 来源(工具/报表) | 实值或估算`。最后一列只能填「实值」或「估算」之一。

## QC 清单
- [ ] 估值/盈利/偿债现金流三组均有覆盖
- [ ] 关键数字标注来源报表与期间
- [ ] 给出趋势而非孤立快照
- [ ] 结尾含组织关键点的 Markdown 表格
- [ ] 实值与估算已区分,且估算未贴工具名伪装成来源

## 常见错误
- 以单季数据外推全年。
- 忽略现金流与利润背离(应计质量)。
- 只看绝对估值不做同业/历史对照。
- 把本可取实值用估算区间替代;给估算贴工具名伪装成来源;数据点无期间。

## 输出末尾自检
报告末尾必须追加固定格式自检块:
【自检】
☑ ETF 层面可取实值均给出实值+截止日,未用估算区间替代
☑ 底层派生估算均已显式标「估算」并说明推算依据
☑ 每个数据点带期间;无未溯源数字
☑ 估值/盈利/偿债现金流三组均覆盖;趋势优先于快照
```

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py -v -p no:cacheprovider"`
Expected: 全部 PASS(既有 P0 4-key / Phase A 5-key / 8-agent 导入 + 新增 fundamentals 测试)。注意:既有 `test_all_four_methodology_keys_present_and_nonempty` 仍应通过(fundamentals 仍非空、仍含"数据源")。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/methodology/fundamentals.md tests/backend/test_methodology.py
git commit -m "feat(methodology): fundamentals.md 收紧——实值优先/估算必标/期间强制/汇总表/自检块"
```

---

### Task 2: sentiment.md 末尾补【自检】块 + 加断言

**Files:**
- Modify: `tradingagents/methodology/sentiment.md`
- Test: `tests/backend/test_methodology.py`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `tests/backend/test_methodology.py` 末尾追加:

```python


def test_sentiment_methodology_has_selfcheck_block():
    text = get_methodology("sentiment")
    assert "## 输出末尾自检" in text
    assert "【自检】" in text
    assert "每个情绪结论可回溯到注入的数据块" in text
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py::test_sentiment_methodology_has_selfcheck_block -v -p no:cacheprovider"`
Expected: FAIL（sentiment.md 当前无 `## 输出末尾自检` / `【自检】`)。

- [ ] **Step 3: 追加节到 `tradingagents/methodology/sentiment.md`** —— 用 Edit 工具,把当前文件最后一行(常见错误最后一条):

old_string:
```
- 忽略数据源时效与样本偏差。
```
new_string:
```
- 忽略数据源时效与样本偏差。

## 输出末尾自检
报告末尾必须追加固定格式自检块:
【自检】
☑ 每个情绪结论可回溯到注入的数据块
☑ 已标注缺失/被关闭的数据源
☑ 区分了散户与机构口径
☑ 全中文,无英文章节标题
```
(其余内容一字不改;保持文件末尾换行。)

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py -v -p no:cacheprovider"`
Expected: 全部 PASS(含 Task 1 的 fundamentals 测试 + 新增 sentiment 测试 + 既有全部)。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/methodology/sentiment.md tests/backend/test_methodology.py
git commit -m "feat(methodology): sentiment.md 末尾补可审计【自检】块"
```

---

### Task 3: 全量回归 + 收尾

**Files:** 无新增(验证)

- [ ] **Step 1: 后端全量回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,0 失败(本特性纯方法论文本,既有结构化/持久化/PDF/方法论测试不受影响)。

- [ ] **Step 2: 确认未误伤 news.md / market.md 等**

Run: `git diff --name-only 606634d..HEAD -- tradingagents/methodology | sort -u`
Expected: 本特性只新增/改动 `fundamentals.md`、`sentiment.md`(连同此前 P0/Phase A 已有的其它方法论文件出现在列表中属正常——重点确认 `news.md`、`market.md` 不在"本次两提交"改动内:`git diff --name-only HEAD~2..HEAD -- tradingagents/methodology` 应仅 `fundamentals.md`、`sentiment.md`)。

- [ ] **Step 3: 手动冒烟(可选,非验收门槛)**

跑一次真实 QQQ 分析,核对 fundamentals 段落:ETF 层面指标是否给实值+截止日(而非区间)、底层加权量是否标「估算」、是否含固定列汇总表与【自检】块;sentiment 段落末尾是否出现【自检】块。单测只覆盖方法论文本加载正确性,不替代真实 LLM 观感。

- [ ] **Step 4: 收尾(如有遗留改动)**

```bash
git status --short
```
无遗留即完成;有则补一次提交。

---

## Self-Review

**Spec 覆盖:**
- fundamentals 实值优先/估算必标/期间强制三条硬规则 → Task 1 Step 3 文件内容"指标口径纪律"三条加粗硬规则 ✅
- fundamentals 固定列汇总表 `指标|数值|期间|来源(工具/报表)|实值或估算` → Task 1 "## 强制输出汇总表" + 测试断言整串 ✅
- fundamentals 对标 market.md 的【自检】块 → Task 1 "## 输出末尾自检" 四条 ✅
- fundamentals QC/常见错误各加一条 → Task 1 QC 清单第 5 条、常见错误第 4 条 ✅
- sentiment 末尾【自检】块 → Task 2 Edit 追加节 ✅
- news.md 不动 → 计划未含;Task 3 Step 2 显式校验 ✅
- 测试(fundamentals 标识 + sentiment 【自检】 + 无回归)→ Task 1/2 断言 + Task 3 全量 ✅
- 范围外(代码/schema/前端/market.md)→ 计划未含 ✅

**Placeholder 扫描:** 无 TBD/TODO;fundamentals.md 完整内容逐字给出;sentiment.md 给出精确 old→new;测试代码完整。

**类型/命名一致:** 测试断言字符串(`实值优先`、`估算·非工具直接读取`、`指标 | 数值 | 期间 | 来源(工具/报表) | 实值或估算`、`期间强制`、`【自检】`、`## 输出末尾自检`、`每个情绪结论可回溯到注入的数据块`)与 Task 1/2 写入的文件内容逐字一致;`get_methodology` key 用 `"fundamentals"`/`"sentiment"` 与既有一致。
