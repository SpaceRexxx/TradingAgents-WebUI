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
