import { describe, it, expect } from "vitest";
import { deriveProgress } from "./progress";

describe("deriveProgress", () => {
  it("marks completed analyst and runs the next agent", () => {
    const p = deriveProgress({ market_report: "done" }, true);
    const market = p.agents.find((a) => a.key === "market")!;
    const social = p.agents.find((a) => a.key === "social")!;
    expect(market.status).toBe("done");
    expect(market.content).toBe("done");
    expect(social.status).toBe("running");
    expect(p.phases.find((x) => x.key === "analysts")!.status).toBe("running");
  });

  it("reads nested debate-state keys", () => {
    const p = deriveProgress(
      {
        market_report: "m",
        sentiment_report: "s",
        news_report: "n",
        fundamentals_report: "f",
        investment_debate_state: { bull_history: "bull", bear_history: "bear" },
      },
      true,
    );
    expect(p.agents.find((a) => a.key === "bull")!.status).toBe("done");
    expect(p.agents.find((a) => a.key === "bear")!.content).toBe("bear");
    expect(p.phases.find((x) => x.key === "analysts")!.status).toBe("done");
    expect(p.phases.find((x) => x.key === "research")!.status).toBe("running");
  });

  it("nothing running once the stream is no longer running", () => {
    const p = deriveProgress({ market_report: "m" }, false);
    expect(p.agents.some((a) => a.status === "running")).toBe(false);
    expect(p.agents.find((a) => a.key === "market")!.status).toBe("done");
  });

  it("keeps live token output running until final node chunk clears it", () => {
    const live = deriveProgress(
      { market_report: "partial", __streaming: { market: true } },
      true,
    );
    expect(live.agents.find((a) => a.key === "market")!.status).toBe("running");
    expect(live.agents.find((a) => a.key === "social")!.status).toBe("pending");
    expect(live.percent).toBe(0);

    const final = deriveProgress(
      { market_report: "complete", __streaming: { market: false } },
      true,
    );
    expect(final.agents.find((a) => a.key === "market")!.status).toBe("done");
    expect(final.agents.find((a) => a.key === "social")!.status).toBe("running");
  });

  it("final decision via final_trade_decision marks portfolio_manager done", () => {
    const p = deriveProgress({ final_trade_decision: "BUY" }, false);
    expect(p.agents.find((a) => a.key === "portfolio_manager")!.status).toBe("done");
    expect(p.phases.find((x) => x.key === "decision")!.status).toBe("done");
  });

  it("percent reflects share of agents with content", () => {
    const empty = deriveProgress({}, true);
    expect(empty.percent).toBe(0);
    const all = deriveProgress(
      {
        market_report: "1",
        sentiment_report: "1",
        news_report: "1",
        fundamentals_report: "1",
        investment_debate_state: {
          bull_history: "1",
          bear_history: "1",
          judge_decision: "1",
        },
        trader_investment_plan: "1",
        risk_debate_state: {
          aggressive_history: "1",
          conservative_history: "1",
          neutral_history: "1",
          judge_decision: "1",
        },
      },
      false,
    );
    expect(all.percent).toBe(100);
  });
});

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
