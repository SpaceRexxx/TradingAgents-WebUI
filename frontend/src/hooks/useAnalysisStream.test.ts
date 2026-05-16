import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAnalysisStream } from "./useAnalysisStream";

class FakeWS {
  static last: FakeWS;
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) { this.url = url; FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.(); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
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
    await waitFor(() => expect(result.current.status).toBe("running"));
  });

  it("disconnect closes + resets", async () => {
    const { result } = renderHook(() => useAnalysisStream());
    act(() => result.current.connect("run-5"));
    act(() => result.current.disconnect());
    expect(FakeWS.last.closed).toBe(true);
    expect(result.current.status).toBe("idle");
  });
});
