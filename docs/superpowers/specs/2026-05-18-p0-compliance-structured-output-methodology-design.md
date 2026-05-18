# P0 升级设计:合规元数据 + 结构化决策表格化 + 分析师方法论外置

**日期:** 2026-05-18
**状态:** 已确认,待实现计划

## 背景

`financial-services-main`(Anthropic "Claude for Financial Services" 参考库)对 `TradingAgents-WebUI` 的对标分析得出 P0 三项低成本高回报升级:

1. 报告注入合规 footer + 运行元数据(命中 gap 6.3:零免责声明、无审计轨迹)
2. `PortfolioDecision` 结构化字段 + PDF/前端表格化 + 新增 conviction 评分(命中 gap 6.4:无置信度、无结构化交易细节)
3. 每个分析师方法论抽成外置 Markdown 文件(命中 gap 6.1,借鉴 financial-services 的 SKILL.md 纪律)

借鉴模式:结构优先且可追溯、合规即设计(非免责声明堆砌)、领域方法论单一来源固化。

## 关键架构决策

**结构化决策如何流到 PDF/前端:携带结构对象(方案 A)。**

`portfolio_manager_node` 当前只把 `PortfolioDecision` 渲染成 markdown 字符串存进 `final_trade_decision`,结构对象被丢弃。本设计让 PM node 额外输出 `final_state["portfolio_decision"]`(dict),PDF 与前端直接读字段渲染表格;markdown 仍保留供 memory log / CLI / 向后兼容。拒绝从 markdown 反向正则解析(脆弱,违背结构优先纪律)。

## 组件 1 — 分析师方法论外置

- 新增目录 `tradingagents/methodology/`,文件:`market.md`、`news.md`、`sentiment.md`、`fundamentals.md`。
- 每个文件结构对标 financial-services SKILL.md 骨架:数据源优先级、指标/口径纪律、QC 清单、常见错误。内容用中文(与现有 prompt 一致)。
- `tradingagents/agents/utils/agent_utils.py` 新增 `get_methodology(key: str) -> str`:
  - 读取 `tradingagents/methodology/<key>.md`。
  - 模块级缓存(读取一次)。
  - 文件缺失/读取失败 → 返回空字符串,不抛异常(优雅降级)。
- 4 个 analyst(`market_analyst.py`、`news_analyst.py`、`sentiment_analyst.py`、`fundamentals_analyst.py`)的 `system_message` 末尾拼接 `get_methodology(<key>)`,与现有 `get_language_instruction()` 同模式。
- 零 LangGraph 图拓扑改动。

## 组件 2 — 结构化决策 + conviction 评分 + 表格化

- `tradingagents/agents/schemas.py`:
  - `PortfolioDecision` 新增 `conviction_score: Optional[int] = Field(default=None, description="信心度评分,1-10 的整数...")`。Field 描述即模型输出指令。
  - `render_pm_decision` 末尾在 `conviction_score is not None` 时追加 `**Conviction**: {n}/10` 行(向后兼容,不破坏现有 section header 解析)。
- `tradingagents/agents/managers/portfolio_manager.py`:
  - 捕获 `invoke_structured_or_freetext` 解析出的结构对象(必要时调整其返回以同时给出 markdown 与对象;若现接口仅返回 markdown,则改为返回 `(markdown, parsed_or_None)`,并更新所有调用方)。
  - node 返回值新增 `portfolio_decision`:结构化时为 `decision.model_dump()`,freetext 回退时为 `None`。
- `backend/services/pdf.py`:
  - 新增"最终决策"区块:若 `final_state["portfolio_decision"]` 存在,渲染 HTML 表格(字段:rating、conviction_score、price_target、stop_loss、breakout_point、time_horizon、outlook_30d/60d/90d);executive_summary、investment_thesis 仍以段落呈现。
  - 若 `portfolio_decision` 缺失(freetext 回退或历史数据)→ 回退到现有 `final_trade_decision` markdown 渲染。
- 前端 `frontend/src/pages/RunReportPage.tsx`:同字段渲染为表格卡片。
- `frontend/src/api/types.ts`:新增 `PortfolioDecision` 类型与可选 `portfolio_decision` 字段。

## 组件 3 — 合规 footer + 运行元数据

- `backend/services/persistence.py` `persist_run()`:
  - 构造 `run_meta` dict:
    - `generated_at`:ISO8601 UTC 时间戳(本次新增,其余字段已有入参)
    - `model`、`provider`(已传入)
    - `token_stats` 摘要(total_tokens、estimated_cost_usd)
    - `disclaimer`:中文固定文案
  - 写入 `serializable["run_meta"]`(落入 `final_state_report.json`)。
  - `generated_at` 一并写入 SQLite 索引(`sqlite_history.index_one_analysis` 如无该列则新增;model/provider 已索引)。
- `backend/services/pdf.py`:页脚区块渲染 `run_meta`(元数据行 + 免责声明,灰色小字)。
- 前端 `RunReportPage.tsx`:报告头或尾显示元数据条 + 免责声明 banner;`types.ts` 加 `run_meta` 类型。
- 免责声明文案(最终):

  > 本报告由 AI 多智能体系统自动生成,仅供研究参考,不构成任何投资、法律或税务建议。所有结论须经合格专业人士复核后方可作为决策依据。

## 测试

- `tests/backend/test_pdf_routes.py`:补结构化决策表格渲染 + footer/免责声明断言;补 `portfolio_decision` 缺失时回退 markdown 的断言。
- `tests/backend/test_persistence.py`:断言 `run_meta`(含 `generated_at`、`disclaimer`)写入 JSON;断言 SQLite 索引含 `generated_at`。
- 新增 `tests/backend/test_methodology.py`:`get_methodology` 正常加载、缺失文件回退空串、缓存行为。
- `schemas` 单测:`conviction_score` 字段存在且可选;`render_pm_decision` 在有/无 conviction 时均产出兼容 markdown。
- 前端 `frontend/src/pages/RunReportPage.test.tsx`:补结构化决策表格 + 元数据/免责声明渲染断言。

## 范围外(YAGNI)

- 分析师级别置信度评分与聚合(P1)
- 数据连接器注册表 / MCP-first 抽象(P1)
- 不可信输入隔离(P1,安全项另议)
- 回测 harness、成本预算闸门、优雅降级(P2)

## 验收标准

- 4 个分析师 system prompt 运行时拼接对应方法论文件内容;文件缺失不致运行失败。
- 结构化决策在 PDF 与前端报告页以表格呈现,含 conviction 评分;freetext 回退路径仍可读。
- `final_state_report.json` 含 `run_meta`(generated_at/model/provider/token摘要/disclaimer);PDF 与前端均显示免责声明与元数据。
- 全部新增/修改测试通过;现有 backend + 前端测试无回归。
