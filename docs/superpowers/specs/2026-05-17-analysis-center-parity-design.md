# Analysis Center Feature-Parity Design

Restore the 10 features the retired Streamlit `webapp.py` analysis screen had but
the React SPA `frontend/src/pages/AnalysisPage.tsx` lacks.

## Scope

Backend: 2 changes.

1. **`GET /api/quote/{ticker}`** — new read-only endpoint. Reuses the exact
   Streamlit logic (`webapp.py:1230-1250`): `to_xueqiu_symbol(ticker)` then
   `opencli xueqiu stock {symbol} -f json` via subprocess, 8s timeout. Adds a
   60s in-process TTL cache keyed by symbol so the SPA can poll without
   spawning a subprocess per call. Returns `{name, price, change,
   changePercent}`. Returns HTTP 204 (no body) when `opencli` is absent, the
   call times out/fails, or output is unparseable — the SPA then hides the
   price line, identical to Streamlit's `None` fallback.

2. **`runner._default_graph_factory`** — pop `selected_analysts` out of the
   merged config and pass it as the `TradingAgentsGraph(selected_analysts,
   config=...)` constructor positional arg (it is NOT a config key). When the
   key is absent or empty, fall back to the engine default
   `["market","social","news","fundamentals"]`. `AnalysisRequest` schema and
   the WS protocol are unchanged.

Frontend: rebuild `AnalysisPage.tsx`; extend `api/types.ts` + `api/client.ts`;
add a progress-inference util; add localStorage prefs.

## Feature -> implementation map

| # | Feature | Wiring |
|---|---------|--------|
| 1 | Analyst checkboxes (4) | `config_overrides.selected_analysts` subset of `["market","social","news","fundamentals"]`, default all 4 |
| 2 | Research depth (jishen0/qianceng1/zhongdeng2/shenru3) | `max_debate_rounds` = `max_risk_discuss_rounds` = depth value |
| 3 | Price lookback slider | 5-120, default 30 -> `lookback_days` |
| 4 | News lookback slider | 1-30, default 7 -> `news_lookback_days` |
| 5 | Trade date | native `<input type=date>`, max = today -> `trade_date` |
| 6 | Position toggle | `config_overrides.has_position` = "已持有" / "未持有" |
| 7 | Live price + Chinese name | `GET /api/quote/{ticker}` on ticker blur; green up / red down; hidden when 204 |
| 8 | Progress stepper + elapsed time | 5 phases + per-second timer from WS connect |
| 9 | Per-agent sidebar + preview + status | client-side inference from WS chunk keys |
| 10 | Elapsed time | same timer as #8 |

## Progress / agent-status inference (no backend change)

The engine already streams per-node deltas (`trading_graph.py:375`,
`graph.stream(...)`), so WS `chunk` payloads already carry
`investment_debate_state` and `risk_debate_state` in addition to the 7 report
keys. `useAnalysisStream` merges every chunk into a flat `report` map, so all
keys are available client-side.

Agent -> signal:

- 市场分析师 <- `market_report`
- 舆情分析师 <- `sentiment_report`
- 新闻分析师 <- `news_report`
- 基本面分析师 <- `fundamentals_report`
- 多头研究员 <- `investment_debate_state.bull_history`
- 空头研究员 <- `investment_debate_state.bear_history`
- 研究经理 <- `investment_debate_state.judge_decision` / `investment_plan`
- 交易员 <- `trader_investment_plan`
- 激进型分析师 <- `risk_debate_state.aggressive_history`
- 保守型分析师 <- `risk_debate_state.conservative_history`
- 中立型分析师 <- `risk_debate_state.neutral_history`
- 投资组合经理 <- `risk_debate_state.judge_decision` / `final_trade_decision`

Phases: 分析师团队 -> 研究团队辩论 -> 交易团队 -> 风险管理辩论 -> 最终决策.
A key appearing marks its agent in-progress; a later-phase key appearing marks
the prior phase complete; terminal `done` marks all complete.

Rejected alternative: emitting new backend `stage` WS events — slightly more
precise but requires engine-graph instrumentation and a WS protocol change.
Not worth it given the stream already exposes the needed keys.

## Persistence

localStorage `ta_prefs` holds `{selectedAnalysts, researchDepth,
lookbackDays, newsLookbackDays, hasPosition}` — the React equivalent of
Streamlit's `ui_prefs`. Restored on mount, written on change.

## Testing

- Backend: pytest for the quote endpoint (mock subprocess: success -> JSON,
  missing opencli -> 204, timeout -> 204) and for the factory threading
  `selected_analysts` into the constructor.
- Frontend: vitest for the inference util (chunk sequences -> expected
  agent/phase status) and AnalysisPage (form -> config_overrides body; quote
  fetch render / hide; stepper transitions).
