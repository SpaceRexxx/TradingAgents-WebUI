# 设计:辩论轮次实时显示

**日期:** 2026-05-19
**状态:** 已确认,待实现计划

## 背景

多头/空头研究辩论与激进/保守/中立风险辩论支持多轮(由 `researchDepth` 控制)。用户希望在运行界面实时看到当前进行到第几轮。轮次信息已存在于运行状态,只需在前端派生并展示;纯前端改动。

## 轮次换算(与 `tradingagents/graph/conditional_logic.py` 实际停止逻辑对齐)

- **研究辩论(多/空)**:每位发言者发言后 `investment_debate_state.count += 1`;`ConditionalLogic.should_continue_debate` 在 `count >= 2 * max_debate_rounds` 时结束辩论转交研究经理。
  - 当前轮 = `min(floor(count / 2) + 1, N)`;当 `count >= 2N` 视为完成,显示 `N / N`。
- **风险辩论(激进/保守/中立)**:每位发言者发言后 `risk_debate_state.count += 1`;`should_continue_risk_analysis` 在 `count >= 3 * max_risk_discuss_rounds` 时结束转交组合经理。
  - 当前轮 = `min(floor(count / 3) + 1, N)`;当 `count >= 3N` 视为完成,显示 `N / N`。

`N` 对两组辩论相同,等于 `prefs.researchDepth`(见下)。

## 数据来源(无需后端/streaming/schema 改动)

- `N`(总轮数):`prefs.researchDepth`。`AnalysisPage.tsx`(约 125-128 行)启动分析时已把 `prefs.researchDepth` 同时作为 `max_debate_rounds` 与 `max_risk_discuss_rounds` 放入 `config_overrides`。前端本就持有该值,运行期间固定不变。
- `count`(已进行的发言数):最新 WebSocket chunk 中的 `investment_debate_state.count` / `risk_debate_state.count`。二者是已注册的 `AgentState` 键(P0 阶段确认 LangGraph 会传播),随 chunk 流到达前端,无需新增字段。

## 组件与数据流

- **`frontend/src/util/progress.ts`**(已负责把 chunk 映射为 agent 状态):新增纯函数派生逻辑,从 chunk 的 `investment_debate_state` / `risk_debate_state` 取 `count`,结合外部传入的 `total`(= researchDepth),产出两个值:
  - `researchRound: { current: number; total: number; done: boolean } | null`
  - `riskRound: { current: number; total: number; done: boolean } | null`
  - 规则:对应 debate 的 `count` 尚未出现(undefined/缺失)或 `total` 无效(<1)时返回 `null`。`current = min(floor(count / k) + 1, total)`(研究 k=2,风险 k=3);`done = count >= k * total`;`done` 时 `current = total`。
- **`frontend/src/pages/AnalysisPage.tsx`** agent 侧栏(`progress.agents.map` 区块,约 361-381 行):
  - 在多头/空头按钮组上方渲染徽标:`研究辩论 第 {current}/{total} 轮`(`done` 时追加 `✓`)。
  - 在激进/保守/中立组上方渲染徽标:`风险辩论 第 {current}/{total} 轮`(`done` 时追加 `✓`)。
  - 对应 round 值为 `null` 时不渲染该徽标(该 debate 尚未开始)。
  - 徽标样式复用既有 `card`/`muted` 等类,轻量、不引入新设计系统元素。
- 改动范围:仅 `progress.ts`(派生函数)+ `AnalysisPage.tsx`(两处徽标渲染 + 把 researchDepth 作为 total 传入派生函数)。不动后端、streaming、schema、PDF、`RunReportPage`。

## 边界与降级

- `count` 缺失或对应 debate 未开始 → 该徽标不渲染(优雅隐藏,不抛错)。
- `researchDepth` 缺省/无效(<1)→ 派生返回 `null`,徽标不渲染。
- `count` 异常超过理论上限 → `min(current, total)` 兜底,不显示越界轮次;`done` 为真时显示 `N/N`。
- `researchDepth` 运行中不变(随 run 固定),使用启动时的值。

## 测试

- **`frontend/src/lib/progress.test.ts`**:针对新派生函数补单测,覆盖:
  - 研究辩论 N=1:count 0/1 → 第 1/1;count 2 → done 第 1/1 ✓。
  - 研究辩论 N=2:count 0/1 → 1/2;count 2/3 → 2/2;count 4 → done 2/2 ✓。
  - 风险辩论 N=1:count 0/1/2 → 1/1;count 3 → done 1/1 ✓。
  - 风险辩论 N=2:count 0..2 → 1/2;count 3..5 → 2/2;count 6 → done 2/2 ✓。
  - 边界:count 缺失 → `null`;total <1 → `null`;count 越界 → 不超过 total。
- 前端 `vitest` 全量无回归;不改后端,后端不受影响。
- `AnalysisPage` 侧栏为纯展示,不强制加渲染测试;逻辑正确性由 `progress.ts` 单测保证。

## 验收标准

- 运行中,研究辩论开始后侧栏多/空组上方出现 `研究辩论 第 X/N 轮`,随 chunk 推进而递增,结束显示 `第 N/N 轮 ✓`;风险辩论同理。
- 两组 debate 未开始时不显示对应徽标。
- `N` 与用户所选研究深度一致;轮次推进与引擎实际停止时机一致(不早于/晚于真实换轮)。
- 新增 `progress.ts` 单测全部通过;前端全量测试无回归。

## 范围外(YAGNI)

- 不写入 PDF / `RunReportPage` / 后端持久化(用户选择"仅实时侧栏")。
- 不修改 `researchDepth → max rounds` 映射。
- 不新增 WebSocket / streaming 字段(`count` 已在流中)。
- 不改 `conditional_logic.py` 的停止逻辑。
