# 多轮辩论未结束前辩论员不显示绿勾 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 辩论阶段 5 个辩论员(bull/bear、aggressive/conservative/neutral)在其多轮辩论整体结束前不显示绿勾(done),改显示进行中(running),辩论 done 后才转 done。

**Architecture:** 纯前端单文件 `frontend/src/util/progress.ts`:在 `deriveProgress` 算出 `agents`/`phases`/`percent`/`researchRound`/`riskRound` 之后、`return` 之前,加一段后处理把"未结束辩论"的辩论员 `done` 降级为 `running`。phases/percent 在此之前已算定,不受影响(符合 spec)。

**Tech Stack:** React + TypeScript + Vitest。

**参考规格:** `docs/superpowers/specs/2026-05-19-debate-agents-no-green-until-debate-done-design.md`

**环境注意:** 前端测试不被 rtk 过滤,正常运行。Bash 工具工作目录在调用间保持(若已 `cd frontend` 勿重复)。分支 `3.1`,仅本地提交,禁止 `git push`,禁止 `--no-verify`。

**已核对基线(真实代码 `frontend/src/util/progress.ts`):**
- 行 150-162:`agents` 由 `AGENT_DEFS.map` 生成,状态规则:`contents[i]&&streaming[i]→running`;`contents[i]→done`;`running&&!anyStreaming&&i===frontier+1→running`;否则 `pending`。`AgentView = {key,label,phase,status,content}`。
- 行 164-174:`phases` 与 `percent` 基于上面的 `agents` 计算(在 researchRound/riskRound 之前)。
- 行 176-189:计算 `researchRound`、`riskRound`(`deriveRound(...) -> DebateRound|null`,`DebateRound={current,total,done}`;研究辩论 `done = count>=2*total`,风险辩论 `done = count>=3*total`;`count` 缺失/`researchDepth` 无效 → `null`)。
- 行 191:`return { agents, phases, percent, researchRound, riskRound };`
- `AGENT_DEFS` 中 `bull`/`bear` 的 `extract` 读 `investment_debate_state.bull_history`/`bear_history`;`aggressive`/`conservative`/`neutral` 读 `risk_debate_state.aggressive_history`/`conservative_history`/`neutral_history`;`research_manager`/`portfolio_manager` 是单独 key(不在辩论员集合内)。
- 已有模块级常量 `RESEARCH_SPEAKERS_PER_ROUND = 2`、`RISK_SPEAKERS_PER_ROUND = 3`(在 PHASE_DEFS 附近)。
- `frontend/src/util/progress.test.ts` 顶部:`import { describe, it, expect } from "vitest"; import { deriveProgress } from "./progress";`,用例直接 `deriveProgress(report, running, researchDepth?)` 断言返回结构。

---

### Task 1: progress.ts 后处理 — 未结束辩论的辩论员降级为 running

**Files:**
- Modify: `frontend/src/util/progress.ts`
- Test: `frontend/src/util/progress.test.ts`(追加)

- [ ] **Step 1: 追加失败测试** —— 在 `frontend/src/util/progress.test.ts` 末尾追加一个新的 `describe` 块(`describe`/`it`/`expect`/`deriveProgress` 已在文件顶部导入,复用,勿重复 import):

```ts

describe("deriveProgress debate agents not done until debate done", () => {
  const statusOf = (p: ReturnType<typeof deriveProgress>, key: string) =>
    p.agents.find((a) => a.key === key)!.status;

  it("research debate ongoing (N=2, count=2): bull/bear running, not done", () => {
    const p = deriveProgress(
      {
        market_report: "m",
        investment_debate_state: { count: 2, bull_history: "b", bear_history: "x" },
      },
      true,
      2,
    );
    expect(p.researchRound).toEqual({ current: 2, total: 2, done: false });
    expect(statusOf(p, "bull")).toBe("running");
    expect(statusOf(p, "bear")).toBe("running");
    // analyst with content unaffected
    expect(statusOf(p, "market")).toBe("done");
  });

  it("research debate done (N=2, count=4): bull/bear done", () => {
    const p = deriveProgress(
      {
        investment_debate_state: { count: 4, bull_history: "b", bear_history: "x" },
      },
      true,
      2,
    );
    expect(p.researchRound).toEqual({ current: 2, total: 2, done: true });
    expect(statusOf(p, "bull")).toBe("done");
    expect(statusOf(p, "bear")).toBe("done");
  });

  it("risk debate ongoing (N=1, count=1): aggressive running; done (count=3): done", () => {
    const ongoing = deriveProgress(
      { risk_debate_state: { count: 1, aggressive_history: "a" } },
      true,
      1,
    );
    expect(ongoing.riskRound).toEqual({ current: 1, total: 1, done: false });
    expect(statusOf(ongoing, "aggressive")).toBe("running");

    const done = deriveProgress(
      { risk_debate_state: { count: 3, aggressive_history: "a" } },
      true,
      1,
    );
    expect(done.riskRound).toEqual({ current: 1, total: 1, done: true });
    expect(statusOf(done, "aggressive")).toBe("done");
  });

  it("research_manager / portfolio_manager NOT downgraded while debate not done", () => {
    const p = deriveProgress(
      {
        investment_debate_state: {
          count: 2,
          bull_history: "b",
          bear_history: "x",
          judge_decision: "jd",
        },
        risk_debate_state: { count: 1, judge_decision: "fd" },
        final_trade_decision: "ftd",
      },
      true,
      2,
    );
    expect(statusOf(p, "research_manager")).toBe("done");
    expect(statusOf(p, "portfolio_manager")).toBe("done");
  });

  it("no regression when researchRound is null (debate not started)", () => {
    const before = deriveProgress({ market_report: "m" }, true);
    const after = deriveProgress({ market_report: "m" }, true, 2);
    expect(after.researchRound).toBeNull();
    expect(statusOf(after, "bull")).toBe(statusOf(before, "bull"));
    expect(statusOf(after, "market")).toBe("done");
  });
});
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: 新块中 "research debate ongoing" / "risk debate ongoing" 用例 FAIL(当前 bull/bear/aggressive 在有 history 内容时被判 `done`,而非 `running`)。其余新用例可能已通过(done/null/manager 情形当前逻辑恰好满足),"ongoing" 两条必失败。

- [ ] **Step 3: 实现后处理**

编辑 `frontend/src/util/progress.ts`:

(a) 在已有模块级常量 `RESEARCH_SPEAKERS_PER_ROUND = 2;` / `RISK_SPEAKERS_PER_ROUND = 3;` 附近,新增两个辩论员集合常量:
```ts
const RESEARCH_DEBATERS = new Set(["bull", "bear"]);
const RISK_DEBATERS = new Set(["aggressive", "conservative", "neutral"]);
```

(b) 在 `deriveProgress` 中,把结尾
```ts
  const riskRound = deriveRound(
    numSub(report, "risk_debate_state", "count"),
    researchDepth,
    RISK_SPEAKERS_PER_ROUND,
  );

  return { agents, phases, percent, researchRound, riskRound };
}
```
改为:
```ts
  const riskRound = deriveRound(
    numSub(report, "risk_debate_state", "count"),
    researchDepth,
    RISK_SPEAKERS_PER_ROUND,
  );

  // While a multi-round debate is still in progress, a debater that has
  // already spoken once is NOT done — it will speak again in later rounds.
  // Downgrade its "done" to "running" until the debate's round is complete.
  // phases/percent were computed above from pre-downgrade statuses and are
  // intentionally left unchanged.
  for (const a of agents) {
    if (a.status !== "done") continue;
    if (RESEARCH_DEBATERS.has(a.key) && researchRound && !researchRound.done) {
      a.status = "running";
    } else if (RISK_DEBATERS.has(a.key) && riskRound && !riskRound.done) {
      a.status = "running";
    }
  }

  return { agents, phases, percent, researchRound, riskRound };
}
```
不改 `agents`/`phases`/`percent`/`researchRound`/`riskRound` 的原计算,不改 `AGENT_DEFS`/`deriveRound`/`numSub`/streaming/frontier 逻辑。

- [ ] **Step 4: 运行,确认通过 + 无回归**

Run: `cd frontend && npx vitest run src/util/progress.test.ts`
Expected: 全部 PASS(既有 deriveProgress 及 debate-round 用例 + 新块 5 条)。
Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误(`for...of` 改 `a.status` 合法;`AgentView.status` 为可写字段)。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/util/progress.ts frontend/src/util/progress.test.ts
git commit -m "fix(progress): 多轮辩论未结束前辩论员显示进行中而非绿勾"
```

---

### Task 2: 全量前端回归 + 收尾

**Files:** 无新增(验证)

- [ ] **Step 1: 前端全量**

Run: `cd frontend && npx vitest run`
Expected: 全部通过,0 失败(本改动只影响 progress.ts 的 5 个辩论员 done→running 降级;`AnalysisPage` 测试若有应不回归——它只渲染 `progress.agents` 状态)。

Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 2: 范围核验**

Run: `git diff --name-only HEAD~1..HEAD | sort -u`
Expected: 仅 `frontend/src/util/progress.ts`、`frontend/src/util/progress.test.ts`。无 `AnalysisPage.tsx`、后端、其它文件。

- [ ] **Step 3: 手动冒烟(可选,非验收门槛)**

研究深度设 ≥2 跑一次分析:观察辩论进行中(第 1/2 轮)时多头/空头(及风险辩论激进/保守/中立)显示沙漏(进行中)而非绿勾;研究/风险辩论各自"第 N/N 轮 ✓"出现后,对应辩论员转绿勾;research_manager/portfolio_manager/4 分析师状态不受影响。单测覆盖逻辑,不替代真实观感。

- [ ] **Step 4: 收尾(如有遗留)**

```bash
git status --short
```
无遗留即完成;有则补一次提交。

---

## Self-Review

**Spec 覆盖:**
- 5 辩论员(bull/bear + aggressive/conservative/neutral)未结束辩论时 done→running → Task 1 Step 3(b) 后处理循环 + Step 1 "ongoing" 用例 ✅
- 辩论 done 后转 done ✓ → Step 3 条件 `!researchRound.done`/`!riskRound.done` + Step 1 "done" 用例 ✅
- research_manager/portfolio_manager/分析师不受影响 → 二者不在 RESEARCH/RISK_DEBATERS 集合 + Step 1 "NOT downgraded" 与 "market done" 断言 ✅
- researchRound/riskRound 为 null 无回归 → Step 3 条件含 `researchRound &&`/`riskRound &&` + Step 1 "no regression when null" 用例 ✅
- percent/phases 不动 → 后处理置于 phases/percent 计算之后、return 之前;注释说明;计划未改其计算 ✅
- 纯前端单文件、不动 AnalysisPage/后端 → Task 2 Step 2 显式核验 ✅
- 测试 + 前端全量 + tsc → Task 1/2 ✅

**Placeholder 扫描:** 无 TBD/TODO;后处理与 5 条测试代码完整;old→new 精确给出。

**类型/命名一致:** `RESEARCH_DEBATERS`/`RISK_DEBATERS`(Set)key 与 `AGENT_DEFS` 中 `bull`/`bear`/`aggressive`/`conservative`/`neutral` 一致;`researchRound`/`riskRound`/`.done` 与既有 `DebateRound` 定义一致;`a.status` 取值 `"running"`/`"done"` 与 `AgentStatus` 一致;测试用 `deriveProgress(report, running, researchDepth?)` 与现签名一致。
