// Client-side inference of per-agent / per-phase progress from the flat
// `report` map that useAnalysisStream builds by merging WS chunk payloads.
// The engine streams per-node LangGraph deltas, so investment_debate_state /
// risk_debate_state keys are present alongside the report keys — no backend
// signal is required.

export type AgentStatus = "pending" | "running" | "done";

export interface AgentView {
  key: string;
  label: string;
  phase: string;
  status: AgentStatus;
  content: string;
}

export interface PhaseView {
  key: string;
  label: string;
  status: AgentStatus;
}

interface AgentDef {
  key: string;
  label: string;
  phase: string;
  extract: (r: Record<string, unknown>) => string;
}

const PHASE_DEFS: { key: string; label: string }[] = [
  { key: "analysts", label: "分析师团队" },
  { key: "research", label: "研究团队辩论" },
  { key: "trader", label: "交易团队" },
  { key: "risk", label: "风险管理辩论" },
  { key: "decision", label: "最终决策" },
];

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function sub(r: Record<string, unknown>, parent: string, child: string): string {
  const p = r[parent];
  if (p && typeof p === "object") return str((p as Record<string, unknown>)[child]);
  return "";
}

function isStreaming(r: Record<string, unknown>, key: string): boolean {
  const state = r.__streaming;
  return Boolean(state && typeof state === "object" && (state as Record<string, unknown>)[key]);
}

const AGENT_DEFS: AgentDef[] = [
  { key: "market", label: "市场分析师", phase: "analysts", extract: (r) => str(r.market_report) },
  { key: "social", label: "舆情分析师", phase: "analysts", extract: (r) => str(r.sentiment_report) },
  { key: "news", label: "新闻分析师", phase: "analysts", extract: (r) => str(r.news_report) },
  { key: "fundamentals", label: "基本面分析师", phase: "analysts", extract: (r) => str(r.fundamentals_report) },
  { key: "bull", label: "多头研究员", phase: "research", extract: (r) => sub(r, "investment_debate_state", "bull_history") },
  { key: "bear", label: "空头研究员", phase: "research", extract: (r) => sub(r, "investment_debate_state", "bear_history") },
  {
    key: "research_manager",
    label: "研究经理",
    phase: "research",
    extract: (r) => sub(r, "investment_debate_state", "judge_decision") || str(r.investment_plan),
  },
  { key: "trader", label: "交易员", phase: "trader", extract: (r) => str(r.trader_investment_plan) },
  { key: "aggressive", label: "激进型分析师", phase: "risk", extract: (r) => sub(r, "risk_debate_state", "aggressive_history") },
  { key: "conservative", label: "保守型分析师", phase: "risk", extract: (r) => sub(r, "risk_debate_state", "conservative_history") },
  { key: "neutral", label: "中立型分析师", phase: "risk", extract: (r) => sub(r, "risk_debate_state", "neutral_history") },
  {
    key: "portfolio_manager",
    label: "投资组合经理",
    phase: "decision",
    extract: (r) => sub(r, "risk_debate_state", "judge_decision") || str(r.final_trade_decision),
  },
];

export interface Progress {
  agents: AgentView[];
  phases: PhaseView[];
  /** 0-100, share of agents that have produced content. */
  percent: number;
}

/**
 * @param report  flat merged WS report map
 * @param running true while the WS stream is still running (not done/aborted/error)
 */
export function deriveProgress(
  report: Record<string, unknown>,
  running: boolean,
): Progress {
  const contents = AGENT_DEFS.map((a) => a.extract(report));
  const streaming = AGENT_DEFS.map((a) => isStreaming(report, a.key));
  const anyStreaming = streaming.some(Boolean);
  // Frontier = index of the last agent that has produced content.
  let frontier = -1;
  contents.forEach((c, i) => {
    if (c) frontier = i;
  });

  const agents: AgentView[] = AGENT_DEFS.map((a, i) => {
    let status: AgentStatus;
    if (contents[i] && streaming[i]) {
      status = "running";
    } else if (contents[i]) {
      status = "done";
    } else if (running && !anyStreaming && i === frontier + 1) {
      status = "running";
    } else {
      status = "pending";
    }
    return { key: a.key, label: a.label, phase: a.phase, status, content: contents[i] };
  });

  const phases: PhaseView[] = PHASE_DEFS.map((p) => {
    const members = agents.filter((a) => a.phase === p.key);
    let status: AgentStatus = "pending";
    if (members.some((m) => m.status === "running")) status = "running";
    else if (members.length > 0 && members.every((m) => m.status === "done")) status = "done";
    else if (members.some((m) => m.status === "done")) status = "running";
    return { key: p.key, label: p.label, status };
  });

  const doneCount = agents.filter((a) => a.status === "done").length;
  const percent = Math.round((doneCount / AGENT_DEFS.length) * 100);

  return { agents, phases, percent };
}
