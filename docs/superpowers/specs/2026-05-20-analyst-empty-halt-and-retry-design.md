# 设计:分析师空内容拦截 + 自动 1 次重试 + 手动重试

**日期:** 2026-05-20
**状态:** 已确认,待实现计划

## 背景

真实运行(300990,2026-05-19)显示市场分析师产出 `market_report=""`(空),系统**静默继续**全部下游 6 个决策类 agent(辩论/研究经理/交易员/PM),完整持久化为"已完成",但其实 1/4 分析师证据基础缺失。前端因 `done` 状态 + 空内容退化为 pending 白圈,完全无可见错误信号。`get_stock_data` + 7 次 `get_indicators` 工具调用都执行了,只是 react agent 最终返回空 content(可能超步 / 模型最后一轮无文本 / 工具循环未收敛)。需求是:**任意一个分析师缺失即停止进入下一步,并提供该分析师重试**。

## 核心规则

1. 每个 analyst node 内部:产出空 report → **自动重试一次**(同节点内再 invoke 一次)。
2. 自动重试后仍空 → 主图在 `Analyst Team → 决策阶段` 之间硬拦截,run 停在 halted 状态,持久化 + 显式标记失败分析师。
3. UI 显式显示失败分析师为 ❌,提供"重试该分析师"按钮;后端按需重跑该单元 + 视情况启动下游子图,同 run_id 全程。
4. 每分析师每 run 上限:1 次原始 + 1 次自动 + 3 次手动 = 5 次尝试。

## 总体形态

**同一 `run_id` 全程**,无 LangGraph checkpointer / 通用 resume 基础设施。手动 retry 通过"独立重跑失败分析师 + 状态补丁 + 启动下游子图"机制实现,不改 LangGraph 基础设施。

## 组件

### 1. 节点内自动 1 次重试(4 个 analyst 文件,各 ~5 行)

在每个 analyst node 内部当前的 `final_report = ...` 之后:
- 若 `final_report.strip() == ""` → `logger.warning("{analyst}: returned empty; retrying once")` + 重新 invoke agent/chain 一次 → 取新 result 作 `final_report`。
- 仍空则保留空串,由 Gate 接管。

实现位置:`tradingagents/agents/analysts/{market,news,fundamentals}_analyst.py`(react agent + invoke)、`sentiment_analyst.py`(ChatPromptTemplate + chain.invoke)。各文件内联(本就有自己的 invoke 调用点),避免抽小工具带来的间接性。

### 2. Analyst Gate(主图条件路由)

在 `tradingagents/graph/setup.py`:把当前 `workflow.add_edge("Analyst Team", "Bull Researcher")` 替换为条件路由——

- 新增 `analyst_gate_decider(state)` 检查 `market_report` / `sentiment_report` / `news_report` / `fundamentals_report` 各自 `strip()` 非空。
- 全 OK → 路由到 `"Bull Researcher"`(继续既有流程)。
- 任一空 → 路由到 `END`,state 同时被 gate 更新 `halted_analysts: list[str]`(空 report 的 analyst key 列表)。
- 路由用 `add_conditional_edges("Analyst Team", analyst_gate_decider, {...})`(Analyst Team 节点本身作为条件源,避免再加 no-op 节点)。

### 3. 状态注册

`tradingagents/agents/utils/agent_states.py`:`AgentState` TypedDict 增 `halted_analysts: Annotated[list[str], "分析师空内容时记录失败键列表"]`(必须注册,LangGraph 才会传播)。

### 4. 持久化

`backend/services/persistence.py` `persist_run`:
- `run_meta.status: "done" | "halted"` —— halted 时 `serializable["run_meta"]["status"] = "halted"`,`serializable["halted_analysts"] = state.get("halted_analysts", [])`。
- SQLite `analyses` 表不改 schema(`created_at`/`model`/`provider` 已有;halted run 的 rating 自然为 None,可接受)。
- 即便 halted,仍写 `final_state_report.json`(便于 retry 加载已成功的 3 份 report)。

### 5. RunHandle 状态扩展

`backend/services/registry.py`(及 RunHandle):
- 新状态 `halted` 与既有 `running`/`done`/`aborted`/`error` 并列。
- `mark_halted(failed_analysts: list[str])`:emit WS event `{type:"halted", failed_analysts:[...]}`,触发 `persist_run` 时带 `halted_analysts`。
- 新增字段:`retry_count_by_analyst: dict[str,int]`(初始 0)、`retry_lock`(asyncio.Lock 或简单 bool;同时只允许一个 retry 任务)。

### 6. Retry endpoint + retry runner

新增 endpoint:`backend/routes/runs.py`
- `POST /api/runs/{run_id}/retry-analyst`,body `{ "analyst": "market" | "social" | "news" | "fundamentals" }`。
- 取 `run_id` 对应 RunHandle;若不存在或状态非 `halted` → 400。
- 该 analyst 已超 3 次手动 retry → 429。
- retry_lock 已被占用 → 409。
- 否则启动后台 task 执行重跑逻辑。

新增 `backend/services/retry_runner.py`:
- 加载现有 final_state(从内存 RunHandle 或从磁盘 `final_state_report.json`)。
- 构造单 analyst node:`create_<analyst>_analyst(llm)` → `.invoke(state)` → 取新 state delta。
- merge:`final_state[<key>_report] = new_report;` `halted_analysts` 更新(去掉已修好的、保留仍空的)。
- 若 4 份现已齐(`halted_analysts == []`)→ 用预编译的"下游子图"(START 直挂 `Bull Researcher`,后续拓扑与现有主图自 Bull Researcher 之后完全一致)`astream` 跑下游 → 持久化 status="done"。
- 仍有空 → `persist_run` 重写 halted 状态(更新 `halted_analysts`)。
- 整个过程经现有 WS 流式推送(同 run_id),前端按既有 chunk 处理逻辑接收 → progress 自然更新。

`tradingagents/graph/setup.py` 新增方法 `build_downstream_workflow()`:复用 Bull Researcher / Bear Researcher / Research Manager / Trader / Aggressive / Conservative / Neutral / Portfolio Manager 节点构造,组装成 `START → Bull Researcher → ...(条件辩论)... → Portfolio Manager → END` 的独立 StateGraph,接收完整 AgentState 作为初始 state。一次编译,缓存复用。

### 7. WS 事件

`WsEvent` 新增 `{ type: "halted", failed_analysts: string[] }`,与既有 `done`/`error`/`aborted` 并列。Retry 触发后,同 run_id 的 WS 继续接收 chunk;若已断开,前端按既有重连逻辑订阅同 run_id。

### 8. 前端

- `frontend/src/api/types.ts`:`AgentStatus` 增 `"failed"`;`WsEvent` union 加 halted 变体;新增 `RetryAnalystRequest`/`RetryAnalystResponse`。
- `frontend/src/util/progress.ts`:**仅当** WS 状态为 `halted`(从 stream hook 传入)时,把 `key ∈ {market,social,news,fundamentals}` 且 `content` 为空的 analyst 状态置 `"failed"`;非 halted 时维持现有 pending/running/done 逻辑(无回归)。
- `frontend/src/hooks/useAnalysisStream.ts`(或等价 stream hook):处理新 `halted` event,把 `stream.status = "halted"`、保存 `failed_analysts`。
- `frontend/src/api/client.ts`:`retryAnalyst(run_id: string, analyst: string)` 调 `POST /api/runs/{run_id}/retry-analyst`。
- `frontend/src/pages/AnalysisPage.tsx`:
  - `statusIcon` 新增 `"failed"` → ❌。
  - `stream.status === "halted"` 时,顶部 banner:"分析师 X / Y 未产出报告,已暂停,请重试"。
  - 每个失败 analyst 旁的按钮 "重试 X 分析师";点击调用 client API;按钮置灰条件:全局 `retrying` 中、或 `retry_count_by_analyst[key] >= 3`(由 RunHandle 通过 WS 或 retry-analyst response 推送)。

### 9. 检测规则

`*_report.strip() == ""` 即判失败(简单、对应观察到的真实失败模式)。后端 logger.warning 在 analyst node 自动重试时 + Gate 决定 halt 时各发一次。

## 测试

### 后端

- **单元 — 自动重试**:mock LLM 让某 analyst 第 1 次返回空、第 2 次返回内容 → final report 非空,logger.warning 被触发。
- **单元 — analyst_gate_decider**:各组合(全 OK / 1 空 / 多空)→ 正确返回 `"Bull Researcher"` 或 END,正确设置 `halted_analysts`。
- **单元 — persist halted**:halted state 经 `persist_run` → JSON 含 `run_meta.status="halted"` 与 `halted_analysts`;SQLite 索引行 rating 为 None,可接受。
- **集成 — retry endpoint**:
  - 单 analyst patch 后仍有空 → 仍 halted,状态更新。
  - 4 份齐后 → 下游子图运行,持久化 status="done"。
  - 并发 retry → 409;超过 3 次 → 429;run 不是 halted 状态 → 400。

### 前端

- `progress.ts`:`stream.status === "halted"` + analyst content 空 → `failed`;非 halted 不影响(回归保护)。
- `AnalysisPage`:halted banner 渲染 + 重试按钮按 `retry_count_by_analyst` 置灰;点击 → 调用 `retryAnalyst`。
- WS event `halted` 被正确解析为 `stream.status = "halted"`。

真实 LLM 行为靠后续 300990 类冒烟。

## 验收标准

- 任一 analyst report 空(自动重试后)→ run 在 Analyst Gate 处 END,不进入下游 6 个决策类 agent;`final_state_report.json` 与 SQLite 显示 halted。
- UI 显示失败 analyst 为 ❌ 并提供重试按钮;点击触发后端 retry。
- retry 单独成功修补该 analyst → 若 4 份齐则下游子图跑完、持久化 done;否则仍 halted。
- 每分析师手动 retry 上限 3 次;并发 retry 拒绝;run 非 halted 状态 retry 拒绝。
- 新增/修改测试通过;前后端无回归。

## 范围外(YAGNI)

- LangGraph checkpointer / 通用 run resume 机制。
- 决策类 agent(trader/PM)空内容(不同根因,另议)。
- 批量 retry endpoint(多分析师一起 retry)。
- Retry 历史/审计日志详细追溯。
- 自动重试次数可调(本批硬编码 1 次)。
- 重新尝试整个 run 的入口(用户可整体重跑一次完整分析)。

## 风险与取舍

- 自动重试会翻倍失败 analyst 的 token 成本(罕见事件);手动 retry 上限 3 次防滥用。
- 下游子图复用现有节点构造,但 LangGraph 状态合并(`messages`/`sender` 等)细节可能有副作用,实现阶段需用集成测试覆盖。
- 同一 run_id 多次 retry+resume → `token_stats` 累加,`run_meta.tokens` 反映全部累计成本(更准确;设计意图保留累加)。
