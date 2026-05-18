# Phase A 实现计划:决策类 Agent 方法论纪律

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 8 个决策类 agent 外置方法论(引用即纪律硬规则 + 角色差异化常见错误 + 末尾自检清单),复用 P0 已建的 `get_methodology()` 加载器。

**Architecture:** 在 `tradingagents/methodology/` 新增 5 个职能合并的 `.md` 文件;在 8 个 agent 的 prompt 末尾(现有 `get_language_instruction()` 之后)追加 `get_methodology("<key>")`,与 4 个分析师完全同一模式。零图拓扑/工具/schema 改动。

**Tech Stack:** Python 3 / LangGraph / pytest;Markdown 方法论文件。

**参考规格:** `docs/superpowers/specs/2026-05-18-phaseA-decision-agent-methodology-design.md`

**环境注意:** `rtk` 代理会过滤 pytest 输出。所有 pytest 必须经 `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest <args> -p no:cacheprovider"`。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**接线统一模式:** 5 个会话类 agent(bull/bear/aggressive/conservative/neutral)的 `prompt` 均为 `f"""...中文撰写。**""" + get_language_instruction()` 结尾后 `llm.invoke(prompt)`。接入方式:把 `+ get_language_instruction()` 改为
```
+ get_language_instruction()
+ "\n\n---\n以下是必须遵循的分析方法论:\n"
+ get_methodology("<key>")
```
并在该文件的 `from tradingagents.agents.utils.agent_utils import ...` 导入项中加入 `get_methodology`。research_manager / trader / portfolio_manager 接入点略有差异,见各自 Task。

---

### Task 1: 新增 5 个方法论文件 + 加载测试

**Files:**
- Create: `tradingagents/methodology/researcher.md`
- Create: `tradingagents/methodology/risk_debate.md`
- Create: `tradingagents/methodology/research_manager.md`
- Create: `tradingagents/methodology/portfolio_manager.md`
- Create: `tradingagents/methodology/trader.md`
- Test: `tests/backend/test_methodology.py`(追加)

- [ ] **Step 1: 追加失败测试** — 在 `tests/backend/test_methodology.py` 末尾追加(`get_methodology` 已在文件顶部从 Task 1/P0 导入,复用,勿重复导入):

```python


def test_phase_a_methodology_keys_present_and_nonempty():
    for key in (
        "researcher",
        "risk_debate",
        "research_manager",
        "portfolio_manager",
        "trader",
    ):
        text = get_methodology(key)
        assert text != "", f"missing methodology: {key}"
        assert "引用即纪律" in text, f"cite-or-flag rule missing in: {key}"
        assert "【自检】" in text, f"self-check block missing in: {key}"
```

- [ ] **Step 2: 运行,确认失败**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py::test_phase_a_methodology_keys_present_and_nonempty -v -p no:cacheprovider"`
Expected: FAIL(文件不存在,`get_methodology` 返回 `""`,断言失败)

- [ ] **Step 3: 创建 5 个方法论文件**(逐字写入以下内容)

`tradingagents/methodology/researcher.md`:
```
# 多空研究员辩论方法论

## 证据来源优先级
1. 四份分析师报告(市场/情绪/新闻/基本面)是唯一一手证据来源。
2. 辩论历史与对方最新论点:用于针对性反驳,不作为新事实来源。
3. 不获取任何新数据;所有论据必须出自上述上游产物。

## 引用即纪律
每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实严禁臆造或估算填充;若必须提及而无来源,显式标注「未溯源」。立场性结论必须引用支撑它的具体上游证据。

## 常见错误(必须规避)
- 确认偏误:只挑选利于己方立场的证据,回避不利数据。
- 无视反方最强论点:绕过而非正面反驳对方核心论据。
- 把情绪/口号当论据:用语气强度替代证据强度。
- 忽略上游分析师已明确指出的风险或利好。
- 罗列数据而不形成有交锋的论证。

## 输出末尾自检(必须在回复末尾逐项标注)
【自检】
☑ 关键论据均锚定到具体分析师报告
☑ 无未溯源数字
☑ 已正面回应反方最强论点
☑ 未回避对己方不利的上游证据
```

`tradingagents/methodology/risk_debate.md`:
```
# 风险辩论方法论(激进/保守/中立通用)

## 证据来源优先级
1. 交易员提案是被评估对象,必须紧扣它展开。
2. 四份分析师报告为风险/收益判断的一手证据。
3. 对方(另两位风险分析师)最新论点用于针对性反驳。
4. 不获取新数据;对方未发言时不得凭空虚构其观点。

## 引用即纪律
每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实严禁臆造或估算填充;若必须提及而无来源,显式标注「未溯源」。立场性结论必须引用支撑它的具体上游证据。

## 常见错误(必须规避)
- 锚定效应:被交易员提案或某一价位锚死,不做独立风险评估。
- 近因效应:过度放大最近一条新闻/行情而忽略整体证据。
- 忽略基率:不参考同类情形的一般性风险概率。
- 风险偏好越界:激进不得滑向无脑保守、保守不得滑向冒进、中立不得放弃明确判断。
- 脱离交易员提案空谈宏观,不落到该笔交易的具体风险。

## 输出末尾自检(必须在回复末尾逐项标注)
【自检】
☑ 论点紧扣交易员提案与具体分析师证据
☑ 无未溯源数字
☑ 已正面回应另两位风险分析师的最新论点
☑ 立场未越界(保持本角色风险偏好)
```

`tradingagents/methodology/research_manager.md`:
```
# 研究经理(投资委员会主席)裁决方法论

## 证据来源优先级
1. 多空辩论历史是裁决依据的主体。
2. 历史教训(若提供)必须纳入考量,避免重复过去错误。
3. 不引入辩论之外的新事实;裁决基于已呈现的论据质量。

## 引用即纪律
每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实严禁臆造或估算填充;若必须提及而无来源,显式标注「未溯源」。评级与逻辑必须引用辩论中的具体论点。

## 常见错误(必须规避)
- 和稀泥:证据不均衡时仍选 Hold 以求稳妥。
- 未说明取舍依据:给出评级却不解释为何采信某一方。
- 忽略辩论中更强论点:被表述强度而非证据强度左右。
- 计划与评级不一致:strategic_actions 的仓位指引与 recommendation 矛盾。
- 不引用历史教训(在提供时)。

## 输出末尾自检(必须在 rationale/strategic_actions 文本末尾逐项标注)
【自检】
☑ 评级基于辩论中最强证据并已说明取舍依据
☑ 无未溯源数字
☑ 执行策略与评级方向/仓位一致
☑ 已纳入历史教训(若提供)
```

`tradingagents/methodology/portfolio_manager.md`:
```
# 投资组合经理最终决策方法论

## 证据来源优先级
1. 风险分析师辩论历史是最终裁决的主体依据。
2. 研究经理投资计划与交易员提案为执行参照。
3. 用户持仓状态(has_position)与历史决策教训必须个性化纳入。
4. 不引入上游之外的新事实。

## 引用即纪律
每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实严禁臆造或估算填充;若必须提及而无来源,显式标注「未溯源」。结论必须锚定风险辩论中的具体证据。

## 常见错误(必须规避)
- 仓位/止损纪律缺失:未给出明确建仓区间或止损位。
- 忽略 has_position:未按"已持有/未持有"做个性化建议。
- 不引用历史决策教训(在提供时)。
- 结论未锚定风险辩论具体证据,泛泛而谈。
- 三段展望(30/60/90 天)与评级/止损相互矛盾。

## 输出末尾自检(必须在 investment_thesis 文本末尾逐项标注)
【自检】
☑ 结论锚定风险辩论具体证据
☑ 无未溯源数字
☑ 已按 has_position 个性化(建仓区间或加/减/保持)
☑ 止损与展望与评级一致;已纳入历史教训(若提供)
```

`tradingagents/methodology/trader.md`:
```
# 交易员执行提案方法论

## 证据来源优先级
1. 研究经理投资计划是提案的直接依据,必须紧扣其评级与执行策略。
2. 分析师团队报告为风险/价位判断的一手证据。
3. 不引入上游之外的新事实。

## 引用即纪律
每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实严禁臆造或估算填充;若必须提及而无来源,显式标注「未溯源」。行动方向必须与研究计划评级一致或显式说明分歧理由。

## 常见错误(必须规避)
- 提案与研究计划脱节:行动方向与评级矛盾且未说明理由。
- 无明确入场/止损:只给方向不给可执行价位区间。
- 忽略分析师报告中的关键风险。
- 用笼统措辞替代具体可执行步骤。

## 输出末尾自检(必须在 reasoning 文本末尾逐项标注)
【自检】
☑ 行动方向与研究计划评级一致(或已说明分歧理由)
☑ 无未溯源数字
☑ 已给出明确入场/止损参考
☑ 已覆盖分析师报告中的关键风险
```

- [ ] **Step 4: 运行,确认通过**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py -v -p no:cacheprovider"`
Expected: PASS(含既有 P0 方法论测试 + 新增 Phase A 测试,全部通过)

- [ ] **Step 5: 提交**

```bash
git add tradingagents/methodology/researcher.md tradingagents/methodology/risk_debate.md tradingagents/methodology/research_manager.md tradingagents/methodology/portfolio_manager.md tradingagents/methodology/trader.md tests/backend/test_methodology.py
git commit -m "feat(methodology): 新增 5 个决策类 agent 方法论文件(引用纪律+常见错误+自检)"
```

---

### Task 2: 接入 researcher.md → 多头/空头研究员

**Files:**
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`

- [ ] **Step 1: bull_researcher.py 接入**

把首行导入
```python
from tradingagents.agents.utils.agent_utils import get_language_instruction
```
改为
```python
from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    get_methodology,
)
```
该文件 `prompt` 以
```python
**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction()
```
结尾。改为:
```python
**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction() + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("researcher")
```
不改其它任何逻辑。

- [ ] **Step 2: bear_researcher.py 接入**

同 Step 1,完全相同的导入改法与 prompt 尾部改法(该文件结构与 bull 镜像一致,`prompt` 同样以 `**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction()` 结尾),key 仍为 `get_methodology("researcher")`。

- [ ] **Step 3: 冒烟 + 回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,无回归(Phase A 起点基线见 Task 5;若失败判断是否本改动引入,导入/语法错误须修正)。

补充模块导入冒烟:
Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/python -c 'import tradingagents.agents.researchers.bull_researcher, tradingagents.agents.researchers.bear_researcher'"`
Expected: 无输出、退出码 0(导入不报错)。

- [ ] **Step 4: 提交**

```bash
git add tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py
git commit -m "feat(researchers): 多空研究员接入 researcher 方法论"
```

---

### Task 3: 接入 risk_debate.md → 三位风险辩论员

**Files:**
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`

- [ ] **Step 1: aggressive_debator.py 接入**

首行导入
```python
from tradingagents.agents.utils.agent_utils import get_language_instruction
```
改为
```python
from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    get_methodology,
)
```
`prompt` 以 `**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction()` 结尾,改为:
```python
**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction() + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("risk_debate")
```

- [ ] **Step 2: conservative_debator.py 接入**

同 Step 1,完全相同的导入改法与 prompt 尾部改法(该文件 `prompt` 同样以 `**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction()` 结尾),key 为 `get_methodology("risk_debate")`。

- [ ] **Step 3: neutral_debator.py 接入**

同 Step 1,完全相同(`prompt` 同样以 `**重要指令：你的所有分析和回复都必须使用中文撰写。**""" + get_language_instruction()` 结尾),key 为 `get_methodology("risk_debate")`。

- [ ] **Step 4: 冒烟 + 回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/python -c 'import tradingagents.agents.risk_mgmt.aggressive_debator, tradingagents.agents.risk_mgmt.conservative_debator, tradingagents.agents.risk_mgmt.neutral_debator'"`
Expected: 退出码 0。

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,无回归。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/agents/risk_mgmt/aggressive_debator.py tradingagents/agents/risk_mgmt/conservative_debator.py tradingagents/agents/risk_mgmt/neutral_debator.py
git commit -m "feat(risk): 三位风险辩论员接入 risk_debate 方法论"
```

---

### Task 4: 接入 research_manager / portfolio_manager / trader

**Files:**
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Modify: `tradingagents/agents/trader/trader.py`

- [ ] **Step 1: research_manager.py 接入**

该文件已有多行导入:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
```
改为加入 `get_methodology`:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_methodology,
)
```
`prompt` 以 `{history}""" + get_language_instruction()` 结尾(随后传入 `invoke_structured_or_freetext`)。把该结尾改为:
```python
{history}""" + get_language_instruction() + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("research_manager")
```
不改 `invoke_structured_or_freetext` 调用与其它逻辑。

- [ ] **Step 2: portfolio_manager.py 接入**

该文件已有多行导入(含 `get_language_instruction`,约第 20 行)。在该导入块加入 `get_methodology`(与现有项同块,保持风格)。

PM 的 `prompt` 是一个 f-string,以 `...{get_language_instruction()}"""` 结尾(约第 106 行),随后第 108 行 `final_trade_decision, decision_obj = invoke_structured_or_freetext_capture(`。在 `prompt = f"""...{get_language_instruction()}"""` 赋值语句之后、`invoke_structured_or_freetext_capture(` 调用之前,新增一行把方法论追加到 prompt:
```python
        prompt = prompt + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("portfolio_manager")
```
(缩进与该函数体一致。)不改 has_position/历史教训/capture 调用等任何现有逻辑。

- [ ] **Step 3: trader.py 接入**

该文件已有多行导入:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
```
改为加入 `get_methodology`:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_methodology,
)
```
`messages` 列表中 system 项的 `content` 以
```python
                    "将你的推理锚定在分析师报告和研究计划中。"
                    + get_language_instruction()
```
结尾。改为:
```python
                    "将你的推理锚定在分析师报告和研究计划中。"
                    + get_language_instruction()
                    + "\n\n---\n以下是必须遵循的分析方法论:\n"
                    + get_methodology("trader")
```
不改 user 项与 `invoke_structured_or_freetext` 调用。

- [ ] **Step 4: 冒烟 + 回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/python -c 'import tradingagents.agents.managers.research_manager, tradingagents.agents.managers.portfolio_manager, tradingagents.agents.trader.trader'"`
Expected: 退出码 0。

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,无回归(尤其 `test_structured_agents.py` / `test_persistence.py` 等不受影响)。

- [ ] **Step 5: 提交**

```bash
git add tradingagents/agents/managers/research_manager.py tradingagents/agents/managers/portfolio_manager.py tradingagents/agents/trader/trader.py
git commit -m "feat(agents): research_manager/portfolio_manager/trader 接入方法论"
```

---

### Task 5: 8-agent 接线回归 + 收尾

**Files:**
- Test: `tests/backend/test_methodology.py`(追加 8-agent 导入守卫)

- [ ] **Step 1: 追加接线回归测试** — 在 `tests/backend/test_methodology.py` 末尾追加:

```python


def test_phase_a_decision_agent_modules_import():
    import importlib
    for mod in (
        "tradingagents.agents.researchers.bull_researcher",
        "tradingagents.agents.researchers.bear_researcher",
        "tradingagents.agents.risk_mgmt.aggressive_debator",
        "tradingagents.agents.risk_mgmt.conservative_debator",
        "tradingagents.agents.risk_mgmt.neutral_debator",
        "tradingagents.agents.managers.research_manager",
        "tradingagents.agents.managers.portfolio_manager",
        "tradingagents.agents.trader.trader",
    ):
        importlib.import_module(mod)
```

- [ ] **Step 2: 运行该测试 + 全量后端回归**

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend/test_methodology.py -v -p no:cacheprovider"`
Expected: 全部 PASS。

Run: `rtk proxy "/opt/homebrew/Caskroom/miniconda/base/bin/pytest tests/backend -q -p no:cacheprovider"`
Expected: 全部通过,0 失败(Phase A 不应触及前端;若有时间可另跑 `cd frontend && npx vitest run` 确认无回归)。

- [ ] **Step 3: 提交**

```bash
git add tests/backend/test_methodology.py
git commit -m "test(methodology): Phase A 8 个决策类 agent 接线回归守卫"
```

- [ ] **Step 4: 手动冒烟(可选,非验收门槛)**

如条件允许,跑一次真实分析,确认 8 个决策类 agent 的输出末尾出现【自检】块、无明显臆造数字。单测只覆盖加载/接线正确性,不替代真实 LLM 观感验证。

---

## Self-Review

**Spec 覆盖:**
- 5 文件划分(researcher/risk_debate/research_manager/portfolio_manager/trader)→ Task 1 ✅
- 四节结构(来源纪律 / 引用即纪律统一硬规则 / 角色差异化常见错误 / 末尾自检)→ Task 1 各文件内容已逐字给出 ✅
- 引用即纪律措辞 5 文件逐字一致 → Task 1 内容中该段落逐字相同;Task 1 测试断言 `"引用即纪律" in text` ✅
- 8 agent 接入(同 `get_language_instruction()` 后追加模式)→ Task 2/3/4,逐 agent 给出精确导入与 prompt 尾部改法 ✅
- 测试(5 key 加载非空 + 8 模块导入)→ Task 1 + Task 5 ✅
- 范围外项(Phase B/C、schema、图拓扑)→ 计划未包含 ✅

**Placeholder 扫描:** 无 TBD/TODO;5 个 md 文件内容逐字给出;每处接线给出精确 old→new。bear/conservative/neutral 的"同 Step 1"均显式重述了结尾匹配串与 key,非占位引用。

**类型/命名一致:** `get_methodology` key 全程一致(researcher / risk_debate / research_manager / portfolio_manager / trader);接线统一串 `"\n\n---\n以下是必须遵循的分析方法论:\n"` 与 P0 分析师完全一致;测试断言的 `引用即纪律` / `【自检】` 与 Task 1 文件内容用词一致。
