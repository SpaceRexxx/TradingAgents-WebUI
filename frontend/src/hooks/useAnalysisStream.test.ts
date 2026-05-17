import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAnalysisStream } from "./useAnalysisStream";

class FakeWS {
  static last: FakeWS;
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number; reason: string; wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) { this.url = url; FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.({ code: 1000, reason: "", wasClean: true }); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
  failClose(code = 1006, reason = "") {
    this.closed = true;
    this.onclose?.({ code, reason, wasClean: false });
  }
}

beforeEach(() => vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket));

describe("useAnalysisStream", () => {
  it("connects to ws path and accumulates chunks", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-1"));
    expect(FakeWS.last.url).toContain("/ws/run-1");
    act(() => FakeWS.last.emit({ type: "status", status: "running" }));
    await waitFor(() => expect(result.current.status).toBe("running"));
    act(() => FakeWS.last.emit({ type: "chunk", payload: { market_report: "m1" } }));
    act(() => FakeWS.last.emit({ type: "chunk", payload: { final_trade_decision: "BUY" } }));
    await waitFor(() => {
      expect(result.current.report.market_report).toBe("m1");
      expect(result.current.report.final_trade_decision).toBe("BUY");
    });
  });

  it("deep-merges live nested chunks", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-live"));
    act(() =>
      FakeWS.last.emit({
        type: "chunk",
        payload: {
          investment_debate_state: { bull_history: "Bull Analyst: buy" },
          __streaming: { bull: true },
        },
      }),
    );
    act(() =>
      FakeWS.last.emit({
        type: "chunk",
        payload: {
          investment_debate_state: { bear_history: "Bear Analyst: sell" },
          __streaming: { bear: true },
        },
      }),
    );
    await waitFor(() => {
      const debate = result.current.report.investment_debate_state as Record<string, string>;
      const streaming = result.current.report.__streaming as Record<string, boolean>;
      expect(debate.bull_history).toBe("Bull Analyst: buy");
      expect(debate.bear_history).toBe("Bear Analyst: sell");
      expect(streaming.bull).toBe(true);
      expect(streaming.bear).toBe(true);
    });
  });

  it("done closes the socket", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-2"));
    act(() => FakeWS.last.emit({ type: "done", status: "done" }));
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(FakeWS.last.closed).toBe(true);
  });

  it("error captures message", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-3"));
    act(() => FakeWS.last.emit({ type: "error", message: "boom" }));
    await waitFor(() => {
      expect(result.current.status).toBe("error");
      expect(result.current.error).toBe("boom");
    });
  });

  it("ping does not change status", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-4"));
    act(() => FakeWS.last.emit({ type: "status", status: "running" }));
    act(() => FakeWS.last.emit({ type: "ping" }));
    await waitFor(() => {
      expect(result.current.status).toBe("running");
      expect(result.current.pingCount).toBe(1);
      expect(result.current.lastPingAt).not.toBeNull();
    });
  });

  it("tracks backend activity chunks", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-activity"));
    act(() =>
      FakeWS.last.emit({
        type: "chunk",
        payload: { __activity: { agent: "conservative", kind: "thinking" } },
      }),
    );
    await waitFor(() => {
      expect(result.current.chunkCount).toBe(1);
      expect(result.current.lastChunkAt).not.toBeNull();
      expect(result.current.lastActivity).toEqual({ agent: "conservative", kind: "thinking" });
    });
  });

  it("disconnect closes + resets", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-5"));
    act(() => result.current.disconnect());
    expect(FakeWS.last.closed).toBe(true);
    expect(result.current.status).toBe("idle");
  });

  it("reports unexpected websocket closes", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-close"));
    act(() => FakeWS.last.failClose(1006, "network lost"));
    await waitFor(() => {
      expect(result.current.status).toBe("error");
      expect(result.current.error).toContain("WebSocket closed unexpectedly");
      expect(result.current.lastClose).toEqual({
        code: 1006,
        reason: "network lost",
        wasClean: false,
      });
    });
  });
});
