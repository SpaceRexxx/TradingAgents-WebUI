# 设计:多轮辩论未结束前辩论员不显示绿勾

**日期:** 2026-05-19
**状态:** 已确认,待实现计划
**前序:** 辩论轮次实时显示(`2026-05-19-debate-round-display`)已完成;本设计修复其衍生的状态展示缺陷。

## 背景

真实运行中观察到:多轮辩论(researchDepth ≥ 2)进行期间,`deriveProgress` 把"已产生 `*_history` 内容且未在 streaming"的辩论员判为 `done`(绿勾 ✓),但这些辩论员在后续轮次还会再发言——绿勾语义误导(整场辩论未结束就显示"完成")。

`frontend/src/util/progress.ts` 现状态逻辑:`contents[i] && streaming[i] → running`;`contents[i] → done`;`running && !anyStreaming && i===frontier+1 → running`;否则 `pending`。多空/风险辩论员第 1 轮发言后即 `contents` 非空 → 立即 `done`。

`progress.ts` 已计算 `researchRound`/`riskRound`(含 `done` 标志,研究辩论 `count ≥ 2N`、风险辩论 `count ≥ 3N` 时为 true),可据此修正。

## 需求

辩论阶段的 5 个辩论员——`bull`、`bear`(研究辩论)与 `aggressive`、`conservative`、`neutral`(风险辩论)——在其所属多轮辩论**整体结束前**,即使已发言,也不显示绿勾;显示"进行中"(`running`,沙漏)。辩论 `done` 后才按正常逻辑允许绿勾(`done`)。`research_manager`、`portfolio_manager`(辩论结束后才发言一次)及 4 个分析师不受影响。

## 范围

纯前端,单文件:`frontend/src/util/progress.ts`(+ 其测试 `frontend/src/util/progress.test.ts`)。不改 `AnalysisPage.tsx`、后端、徽标文案、percent/phases/streaming 逻辑。

## 实现

在 `deriveProgress` 中,已计算出 `agents`、`researchRound`、`riskRound` 之后、`return` 之前,新增后处理:

- 模块级常量:`RESEARCH_DEBATERS = ["bull", "bear"]`、`RISK_DEBATERS = ["aggressive", "conservative", "neutral"]`(以 `Set` 判定)。
- 遍历 `agents`,对每个 agent:
  - 若 `agent.key ∈ RESEARCH_DEBATERS` 且 `researchRound` 非 null 且 `researchRound.done === false` 且 `agent.status === "done"` → 将 `agent.status` 改为 `"running"`。
  - 若 `agent.key ∈ RISK_DEBATERS` 且 `riskRound` 非 null 且 `riskRound.done === false` 且 `agent.status === "done"` → 改为 `"running"`。
  - 其它情况不动。
- 不修改 `streaming`/`frontier`/`percent`/`phases` 的计算;`research_manager`/`portfolio_manager`/分析师不在两个 Set 中,天然不受影响。
- `researchRound`/`riskRound` 为 `null`(辩论未开始,`count` 缺失或 researchDepth 无效)时条件不成立,行为与改前一致(无回归)。

## 边界

- `researchRound.done === true`(研究辩论 count ≥ 2N):不降级,`bull`/`bear` 可显示 `done` ✓,与"研究辩论 第 N/N 轮 ✓"徽标一致。
- 辩论进行中(第 1/2/3 轮,未 done):已发言辩论员全部显示 `running`(沙漏);未发言的辩论员仍按原逻辑(`pending` 或 frontier-running)。
- `percent` 不变(仍按"有内容"占比计):本设计只改单个 agent 的展示状态,不动 percent(YAGNI;如需联动另议)。

## 测试

`frontend/src/util/progress.test.ts` 追加:

- 研究辩论 `researchDepth=2`、`investment_debate_state.count=2`(第 2 轮,未 done):`bull`/`bear` 有 history 内容 → 状态 `"running"`(非 `"done"`);`market_report` 已完成的 `market` 仍 `"done"`(未被波及)。
- 研究辩论 done(`count=4`,N=2):`bull`/`bear` 有内容 → `"done"`。
- 风险辩论 `researchDepth=1`、`risk_debate_state.count=1`(未 done):`aggressive` 有内容 → `"running"`;`count=3`(done)→ `"done"`。
- 辩论未 done 但 `research_manager`/`portfolio_manager` 已有内容(judge_decision/final_trade_decision)→ 仍 `"done"`(不被误降级)。
- `researchRound===null`(无 `investment_debate_state` 或无 researchDepth)→ 状态与改前一致(回归保护)。

前端 `vitest` 全量通过、`tsc --noEmit` 无错误;不改后端,后端不受影响。

## 验收标准

- 多轮辩论(N≥2)进行中,5 个辩论员中已发言者显示 `running`(沙漏)而非 `done`(绿勾);对应辩论 `done` 后转 `done` ✓。
- `research_manager`/`portfolio_manager`/4 分析师状态不受本改动影响。
- `researchRound`/`riskRound` 为 null 时行为与改前一致(无回归)。
- 新增/修改测试通过;前端全量无回归;`tsc` 干净。

## 范围外(YAGNI)

- `AnalysisPage.tsx`、徽标文案、后端、streaming/frontier/percent/phases 逻辑。
- 结构化 agent 的 streaming(已知固有限制,另议)。
- 任何后端/schema/图拓扑改动。
