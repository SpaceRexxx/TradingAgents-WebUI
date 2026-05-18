# Phase A 设计:决策类 Agent 方法论纪律(引用即纪律 + 常见错误 + 输出自检)

**日期:** 2026-05-18
**状态:** 已确认,待实现计划
**前序:** P0(`2026-05-18-p0-compliance-structured-output-methodology-design.md`)已完成并在真实运行中验证(`portfolio_decision`/`run_meta` 端到端生效)。

## 背景

P0 已为 4 个分析师(market/news/sentiment/fundamentals)外置方法论。本阶段(三阶段计划的 Phase A)把同样的方法论纪律推广到 8 个决策类 agent,提升其专业度与准确度。借鉴 financial-services-main 的:SKILL.md 骨架、cite-or-flag 引用纪律、常见错误(反模式)清单、输出自检清单。

对应用户诉求:item 1(所有 agent 方法论外置)+ item 2(引用即纪律硬规则 + 输出自检)+ item 5(常见错误清单推广到决策类 agent)。

**三阶段计划:**
- **Phase A(本 spec):** item 1+2+5 — 8 个决策类 agent 方法论文件(纯 prompt/文件改动,低风险)。
- **Phase B(后续独立 spec):** item 3 — news/sentiment 不可信输入隔离(含安全)。
- **Phase C(后续独立 spec):** item 4 — 决策类 agent 结构化分步自验证(schema/QC 字段)。

## 范围

覆盖 8 个 agent,经 5 个职能合并的方法论文件(镜像角色共用,差异由各 agent 现有 prompt 负责):

| 文件(`tradingagents/methodology/`) | 服务的 agent |
|---|---|
| `researcher.md` | `researchers/bull_researcher.py`, `researchers/bear_researcher.py` |
| `risk_debate.md` | `risk_mgmt/aggressive_debator.py`, `risk_mgmt/conservative_debator.py`, `risk_mgmt/neutral_debator.py` |
| `research_manager.md` | `managers/research_manager.py` |
| `portfolio_manager.md` | `managers/portfolio_manager.py` |
| `trader.md` | `trader/trader.py` |

排除:`analysts/social_media_analyst.py`(sentiment 的遗留别名,不生效)。4 个分析师已在 P0 完成,不动。

## 复用既有机制

复用 P0 已建的 `tradingagents/agents/utils/agent_utils.py:get_methodology(key)` 加载器(`@lru_cache`、文件缺失返回 `""` 优雅降级)。本阶段零新机制——只新增 5 个 `.md` 文件并在 8 个 agent 的 system prompt 末尾接入。

## 每个方法论文件的结构

对标 financial-services SKILL.md 骨架,中文撰写(与现有 prompt 一致),四节:

### 1. 证据来源优先级与纪律
这些 agent 不获取原始市场数据,而是在上游产物之上推理(分析师报告、研究计划、辩论历史、交易员提案、历史记忆)。规定结论必须锚定到具体上游产物;明确各角色应优先依据哪些上游输入。

### 2. 引用即纪律(硬规则,统一措辞)
8 个 agent 通用同一条硬规则,逐字一致:

> **引用即纪律:** 每个事实陈述与数字必须可追溯到具体上游产物(分析师报告/研究计划/辩论历史/交易员提案/历史记忆)。上游产物中不存在的数字或事实**严禁臆造或估算填充**;若必须提及而无来源,显式标注「未溯源」。立场性结论必须引用支撑它的具体上游证据。

### 3. 常见错误清单(按角色差异化,item 5)
每个文件列出该角色的反模式(必须规避):
- **researcher.md:** 确认偏误(只挑利己证据)、无视反方最强论点、把情绪当论据、忽略上游分析师已指出的风险。
- **risk_debate.md:** 锚定效应、近因效应、忽略基率、风险偏好越界(激进/保守/中立各自不得滑向对立姿态)、脱离交易员提案空谈。
- **research_manager.md:** 不真正裁决/和稀泥、未说明选择某方的取舍依据、忽略辩论中更强论点、计划与评级不一致。
- **portfolio_manager.md:** 仓位/止损纪律缺失、忽略 `has_position` 个性化、不引用历史决策教训、结论未锚定风险辩论具体证据。
- **trader.md:** 提案与研究计划脱节、无明确入场/止损区间、忽略分析师报告中的关键风险、行动与评级方向矛盾。

### 4. 输出末尾自检清单(item 2)
每个文件末尾给出该角色 3-4 条固定自检项,并在文件中明确指示:**agent 必须在其输出报告的末尾追加一个固定格式自检块**,逐项标注。示例(researcher):

```
【自检】
☑ 关键论据均锚定到具体分析师报告
☑ 无未溯源数字
☑ 已正面回应反方最强论点
```

各角色自检项与其常见错误对应。该自检块是可审计、可人工抽查的轻量约束;不引入结构化 schema 字段(那属于 Phase C)。

## 接入方式

8 个 agent 的 system prompt / system_message,在现有 `get_language_instruction()`(或其等价位置)之后,追加与 4 个分析师完全相同的拼接模式:

```
+ get_language_instruction()
+ "\n\n---\n以下是必须遵循的分析方法论:\n"
+ get_methodology("<key>")
```

逐 agent 说明:
- `bull_researcher.py` / `bear_researcher.py`:在其 system prompt 构造末尾追加 `get_methodology("researcher")`。
- `aggressive_debator.py` / `conservative_debator.py` / `neutral_debator.py`:追加 `get_methodology("risk_debate")`。
- `research_manager.py`:追加 `get_methodology("research_manager")`。
- `portfolio_manager.py`:其 prompt 是以 `{get_language_instruction()}` 结尾的 f-string;在该 f-string 末尾追加方法论文本(`get_methodology("portfolio_manager")`),保持 has_position/历史教训等现有逻辑不变。
- `trader.py`:追加 `get_methodology("trader")`。

实现者须先读取每个 agent 文件,按其真实 prompt 构造方式接入(部分用 ChatPromptTemplate、部分用字符串拼接、PM 用 f-string),不改 LangGraph 图拓扑、不改工具列表、不改各 agent 业务逻辑。`get_methodology` 导入加入各文件既有的 `agent_utils` 导入项。

## 测试

- 扩展 `tests/backend/test_methodology.py`:
  - 5 个新 key(researcher/risk_debate/research_manager/portfolio_manager/trader)`get_methodology` 加载非空。
  - 8 个 agent 模块 `importlib.import_module` 不报错(接线回归守卫)。
- 后端全量 `pytest tests/backend` 无回归;前端 `vitest` 无回归(本阶段不应触及前端)。
- 不做真实 LLM 行为断言(单测覆盖加载/接线正确性;真实效果靠后续手动冒烟,不在本阶段验收)。

## 验收标准

- `tradingagents/methodology/` 新增 5 个文件,各含四节(来源纪律 / 引用即纪律统一硬规则 / 角色差异化常见错误 / 末尾自检清单),中文。
- 8 个 agent 的 prompt 运行时拼接对应方法论文本;文件缺失不致运行失败(复用既有优雅降级)。
- 引用即纪律措辞在 5 个文件中逐字一致。
- 全部新增/修改测试通过;后端 + 前端无回归。

## 范围外(YAGNI)

- 不可信输入隔离 / prompt injection 防护(Phase B)。
- 决策类 agent 结构化分步自验证字段、schema 改动(Phase C)。
- 新增任何 Pydantic 字段或图拓扑/工具改动。
- 4 个分析师方法论文件的改写(P0 已完成,保持现状)。
