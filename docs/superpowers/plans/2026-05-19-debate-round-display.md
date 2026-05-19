# 辩论轮次实时显示 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在运行界面 agent 侧栏实时显示研究辩论(多/空)与风险辩论(激进/保守/中立)当前进行到第几轮。

**Architecture:** 纯前端。`frontend/src/util/progress.ts` 的 `deriveProgress` 增加可选 `researchDepth` 入参,从已合并的 `report` 中读取 `investment_debate_state.count` / `risk_debate_state.count`,按引擎停止逻辑(研究 `2N`、风险 `3N`)派生 `researchRound` / `riskRound` 并随 `Progress` 返回;`AnalysisPage.tsx` 在 agent 侧栏对应分组上方渲染两个徽标。不改后端/streaming/schema/PDF。

**Tech Stack:** React + TypeScript + Vitest。

**参考规格:** `docs/superpowers/specs/2026-05-19-debate-round-display-design.md`

**环境注意:** 前端测试不被 rtk 过滤,正常运行。当前目录在仓库根 `/Users/tonniclaw/TradingAgents-WebUI`;前端命令需 `cd frontend` 后执行(注意:Bash 工具的工作目录在调用间保持,若上一条已 `cd frontend` 则勿重复 cd)。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**关键事实(已核对真实代码):**
- `frontend/src/util/progress.ts` 现有 `deriveProgress(report: Record<string, unknown>, running: boolean): Progress`,`Progress = { agents, phases, percent }`。已有内部辅助 `str(v)`、`sub(r,parent,child)`(仅取字符串子键)。`AGENT_DEFS` 中 research 阶段 agent 的 `phase==="research"`(bull/bear/research_manager),risk 阶段 `phase==="risk"`(aggressive/conservative/neutral)。
- `frontend/src/pages/AnalysisPage.tsx`:第 5 行 `import { deriveProgress, type AgentStatus } from "../util/progress";`;第 79-81 行 `const progress = useMemo(() => deriveProgress(stream.report, running), [stream.report, running]);`;侧栏在约 365 行 `progress.agents.map((a) => (<button .../>))`;`prefs.researchDepth` 在第 125-128 行作为 `max_debate_rounds`/`max_risk_discuss_rounds` 放入 `config_overrides`,组件内可直接读 `prefs.researchDepth`。
- `count` 路径:`report.investment_debate_state.count` / `report.risk_debate_state.count`(数值)。对应 debate 未开始时该 parent 键不存在。
- 测试风格(`frontend/src/util/progress.test.ts`):`import { describe, it, expect } from "vitest"; import { deriveProgress } from "./progress";`,直接 `deriveProgress({...}, true)` 断言返回结构。

---

### Task 1: progress.ts 派生辩论轮次

**Files:**
- Modify: `frontend/src/util/progress.ts`
- Test: `frontend/src/util/progress.test.ts`(追加)

- [ ] **Step 1: 追加失败测试** — 在 `frontend/src/util/progress.test.ts` 末尾追加一个新的 `describe` 块(`deriveProgress`/`describe`/`it`/`expect` 已在文件顶部导入,复用):

```ts

describe("deriveProgress debate rounds", () => {
  it("returns null rounds when debate state absent", () => {
    const p = deriveProgress({ market_report: "x" }, true, 2);
    expect(p.researchRound).toBeNull();
    expect(p.riskRound).toBeNull();
  });

  it("returns null rounds when researchDepth missing/invalid", () => {
    const p = deriveProgress(
      { investment_debate_state: { count: 1 } },
      true,
    );
    expect(p.researchRound).toBeNull();
    const p0 = deriveProgress(
      { investment_debate_state: { count: 1 } },
      true,
      0,
    );
    expect(p0.researchRound).toBeNull();
  });

  it("research debate N=1: count 0/1 -> round 1/1, count 2 -> done", () => {
    expect(
      deriveProgress({ investment_debate_state: { count: 0 } }, true, 1)
        .researchRound,
    ).toEqual({ current: 1, total: 1, done: false });
    expect(
      deriveProgress({ investment_debate_state: { count: 1 } }, true, 1)
        .researchRound,
    ).toEqual({ current: 1, total: 1, done: false });
    expect(
      deriveProgress({ investment_debate_state: { count: 2 } }, true, 1)
        .researchRound,
    ).toEqual({ current: 1, total: 1, done: true });
  });

  it("research debate N=2: count 0..4 progression", () => {
    const r = (c: number) =>
      deriveProgress({ investment_debate_state: { count: c } }, true, 2)
        .researchRound;
    expect(r(0)).toEqual({ current: 1, total: 2, done: false });
    expect(r(1)).toEqual({ current: 1, total: 2, done: false });
    expect(r(2)).toEqual({ current: 2, total: 2, done: false });
    expect(r(3)).toEqual({ current: 2, total: 2, done: false });
    expect(r(4)).toEqual({ current: 2, total: 2, done: true });
  });

  it("risk debate N=1: count 0..2 -> 1/1, count 3 -> done", () => {
    const r = (c: number) =>
      deriveProgress({ risk_debate_state: { count: c } }, true, 1).riskRound;
    expect(r(0)).toEqual({ current: 1, total: 1, done: false });
    expect(r(2)).toEqual({ current: 1, total: 1, done: false });
    expect(r(3)).toEqual({ current: 1, total: 1, done: true });
  });

  it("risk debate N=2: count 0..6 progression", () => {
    const r = (c: number) =>
      deriveProgress({ risk_debate_state: { count: c } }, true, 2).riskRound;
    expect(r(0)).toEqual({ current: 1, total: 2, done: false });
    expect(r(2)).toEqual({ current: 1, total: 2, done: false });
    expect(r(3)).toEqual({ current: 2, total: 2, done: false });
    expect(r(5)).toEqual({ current: 2, total: 2, done: false });
    expect(r(6)).toEqual({ current: 2, total: 2, done: true });
  });

  it("clamps out-of-range count to total", () => {
    expect(
      deriveProgress({ investment_debate_state: { count: 99 } }, true, 2)
        .researchRound,
    ).toEqual({ current: 2, total: 2, done: true });
  });

  it("omitting researchDepth keeps existing 2-arg behavior", () => {
    const p = deriveProgress({ market_report: "done" }, true);
    expect(p.agents.find((a) => a.key === "market")!.status).toBe("done");
    expect(p.researchRound).toBeNull();
    expect(p.riskRound).toBeNull();
  });
});
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: FAIL（`p.researchRound` / `p.riskRound` 为 `undefined`,断言不通过；3-arg 调用类型/行为不存在）。

- [ ] **Step 3: 实现** — 编辑 `frontend/src/util/progress.ts`:

(a) 在 `PhaseView` 接口之后(约第 21 行后)新增类型:

```ts
export interface DebateRound {
  current: number;
  total: number;
  done: boolean;
}
```

(b) 在 `sub(...)` 函数之后新增两个纯函数:

```ts
function numSub(
  r: Record<string, unknown>,
  parent: string,
  child: string,
): number | null {
  const p = r[parent];
  if (p && typeof p === "object") {
    const v = (p as Record<string, unknown>)[child];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

function deriveRound(
  count: number | null,
  total: number | undefined,
  speakersPerRound: number,
): DebateRound | null {
  if (
    count === null ||
    total === undefined ||
    !Number.isFinite(total) ||
    total < 1
  ) {
    return null;
  }
  const limit = speakersPerRound * total;
  const done = count >= limit;
  const current = done
    ? total
    : Math.min(Math.floor(count / speakersPerRound) + 1, total);
  return { current, total, done };
}
```

(c) 在 `Progress` 接口中新增两个字段(放在 `percent` 后):

```ts
export interface Progress {
  agents: AgentView[];
  phases: PhaseView[];
  /** 0-100, share of agents that have produced content. */
  percent: number;
  /** 研究辩论(多/空)轮次进度;debate 未开始或 researchDepth 无效时为 null。 */
  researchRound: DebateRound | null;
  /** 风险辩论(激进/保守/中立)轮次进度;同上。 */
  riskRound: DebateRound | null;
}
```

(d) 修改 `deriveProgress` 签名增加可选第三参,并在 `return` 中带上两个字段:

把
```ts
export function deriveProgress(
  report: Record<string, unknown>,
  running: boolean,
): Progress {
```
改为
```ts
export function deriveProgress(
  report: Record<string, unknown>,
  running: boolean,
  researchDepth?: number,
): Progress {
```

把结尾
```ts
  return { agents, phases, percent };
}
```
改为
```ts
  const researchRound = deriveRound(
    numSub(report, "investment_debate_state", "count"),
    researchDepth,
    2,
  );
  const riskRound = deriveRound(
    numSub(report, "risk_debate_state", "count"),
    researchDepth,
    3,
  );

  return { agents, phases, percent, researchRound, riskRound };
}
```

不改其它逻辑(agents/phases/percent 计算保持原样)。

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: 全部 PASS(既有 deriveProgress 测试 + 新增 debate rounds 测试)。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/util/progress.ts frontend/src/util/progress.test.ts
git commit -m "feat(progress): 从 debate count 派生 research/risk 轮次进度"
```

---

### Task 2: AnalysisPage 侧栏渲染轮次徽标

**Files:**
- Modify: `frontend/src/pages/AnalysisPage.tsx`

- [ ] **Step 1: 传入 researchDepth** — `frontend/src/pages/AnalysisPage.tsx` 第 79-81 行当前为:

```tsx
  const progress = useMemo(
    () => deriveProgress(stream.report, running),
    [stream.report, running],
  );
```
改为(把 `prefs.researchDepth` 作为第三参传入,并加入依赖数组):

```tsx
  const progress = useMemo(
    () => deriveProgress(stream.report, running, prefs.researchDepth),
    [stream.report, running, prefs.researchDepth],
  );
```
(`prefs` 在该组件内已可用 —— 第 125-128 行已使用 `prefs.researchDepth`。)

- [ ] **Step 2: 渲染两个徽标** — 侧栏当前(约 364-381 行)为:

```tsx
          <div className="card col" style={{ gap: 4, minWidth: 180 }}>
            {progress.agents.map((a) => (
              <button
                key={a.key}
                onClick={() => setSelectedAgent(a.key)}
                className="btn-ghost"
                aria-label={a.label}
                style={{
                  textAlign: "left",
                  border: 0,
                  background: a.key === selectedAgent ? "var(--c-surface-2)" : "transparent",
                  fontWeight: a.key === selectedAgent ? 700 : 400,
                }}
              >
                {statusIcon(a.status)} {a.label}
              </button>
            ))}
          </div>
```

替换为:在遍历 agent 时,遇到该 agent 是其所属 debate 分组的第一个(`bull` 之前插研究辩论徽标,`aggressive` 之前插风险辩论徽标)时,先渲染对应徽标。改为:

```tsx
          <div className="card col" style={{ gap: 4, minWidth: 180 }}>
            {progress.agents.map((a) => (
              <Fragment key={a.key}>
                {a.key === "bull" && progress.researchRound && (
                  <div className="muted" style={{ fontSize: "var(--fz-sm)", padding: "2px 6px" }}>
                    研究辩论 第 {progress.researchRound.current}/{progress.researchRound.total} 轮
                    {progress.researchRound.done ? " ✓" : ""}
                  </div>
                )}
                {a.key === "aggressive" && progress.riskRound && (
                  <div className="muted" style={{ fontSize: "var(--fz-sm)", padding: "2px 6px" }}>
                    风险辩论 第 {progress.riskRound.current}/{progress.riskRound.total} 轮
                    {progress.riskRound.done ? " ✓" : ""}
                  </div>
                )}
                <button
                  onClick={() => setSelectedAgent(a.key)}
                  className="btn-ghost"
                  aria-label={a.label}
                  style={{
                    textAlign: "left",
                    border: 0,
                    background: a.key === selectedAgent ? "var(--c-surface-2)" : "transparent",
                    fontWeight: a.key === selectedAgent ? 700 : 400,
                  }}
                >
                  {statusIcon(a.status)} {a.label}
                </button>
              </Fragment>
            ))}
          </div>
```

(注意:`key` 从 `<button>` 移到外层 `<Fragment>`。)

- [ ] **Step 3: 确保 `Fragment` 已导入** — 检查 `AnalysisPage.tsx` 顶部的 React 导入。若已 `import { useMemo, ... } from "react";` 一类具名导入,则把 `Fragment` 加入该具名导入列表;若使用 `import React from "react"` 则改用 `<React.Fragment>` 替代 `<Fragment>`。务必使该文件中 `Fragment` 可用且不破坏既有导入风格。验证方式见 Step 4 的 tsc。

- [ ] **Step 4: 类型检查 + 前端全量回归**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误。

Run: `cd frontend && npx vitest run`
Expected: 全量通过(基线 56 passed;本任务不加测试,期望 56 passed,0 failed)。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/AnalysisPage.tsx
git commit -m "feat(ui): agent 侧栏实时显示研究/风险辩论轮次徽标"
```

---

### Task 3: 全量回归 + 收尾

**Files:** 无新增(验证)

- [ ] **Step 1: 前端全量**

Run: `cd frontend && npx vitest run`
Expected: 全部通过,0 失败。

Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 2: 后端无副作用确认**

本特性纯前端,未改后端。无需跑后端;若需快速确认未误改:`git diff --name-only 606634d..HEAD -- backend tradingagents | head` 应不包含本特性引入的后端改动(仅此前 P0/PhaseA 的既有改动)。

- [ ] **Step 3: 手动冒烟(可选,非验收门槛)**

起前后端,设研究深度 ≥ 2 跑一次分析,确认:研究辩论开始后侧栏多头上方出现 `研究辩论 第 X/N 轮` 并随推进递增、结束显示 `✓`;风险辩论同理;深度=1 时显示 `第 1/1 轮`;debate 未开始时不显示徽标。单测覆盖换算逻辑,不替代真实观感。

- [ ] **Step 4: 收尾(如有遗留改动)**

```bash
git status --short
```
若无遗留改动则本计划完成;有则按改动内容补一次提交。

---

## Self-Review

**Spec 覆盖:**
- 轮次换算(研究 `/2`、风险 `/3`、`min(...,N)`、`done` 时 `N/N`)→ Task 1 `deriveRound` + 单测各档 ✅
- 数据来源(`count` 取 `*_debate_state.count`;`N=prefs.researchDepth`)→ Task 1 `numSub` + Task 2 传参 ✅
- 组件与数据流(`progress.ts` 派生 + `AnalysisPage` 两徽标贴各自分组)→ Task 1 + Task 2 ✅
- 边界与降级(count 缺失/total 无效→null 隐藏;越界 clamp)→ Task 1 单测"absent"/"invalid"/"clamps" ✅
- 测试(progress 单测覆盖各档+边界;前端全量无回归;不强制 AnalysisPage 渲染测试)→ Task 1 + Task 3 ✅
- 范围外(PDF/报告/后端/streaming/映射不动)→ 计划未含 ✅

**Placeholder 扫描:** 无 TBD/TODO;每步给出完整代码与精确 old→new。

**类型/命名一致:** `DebateRound { current,total,done }`、`Progress.researchRound/riskRound`、`deriveProgress(report,running,researchDepth?)`、`numSub`/`deriveRound` 全程一致;Task 2 渲染读取的字段名与 Task 1 定义一致;研究 speakersPerRound=2、风险=3 与 spec/`conditional_logic` 一致。
