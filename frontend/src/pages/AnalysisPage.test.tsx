import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import AnalysisPage from "./AnalysisPage";

class FakeWS {
  static last: FakeWS;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.(); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
});

it("start posts the form, connects stream, renders markdown chunks, reaches done", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r1" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);

  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("Ticker"), "AAPL");
  await userEvent.type(screen.getByLabelText("交易日期"), "2026-01-02");
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));

  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/analysis/start", expect.objectContaining({ method: "POST" })));
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r1"));

  FakeWS.last.emit({ type: "status", status: "running" });
  FakeWS.last.emit({ type: "chunk", payload: { market_report: "# Market\nstrong buy" } });
  await waitFor(() => expect(screen.getByRole("heading", { name: "Market" })).toBeInTheDocument());

  FakeWS.last.emit({ type: "done", status: "done" });
  await waitFor(() => expect(screen.getByText(/已完成/)).toBeInTheDocument());
});

it("abort posts to the abort endpoint", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r2", accepted: true }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("Ticker"), "AAPL");
  await userEvent.type(screen.getByLabelText("交易日期"), "2026-01-02");
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r2"));
  FakeWS.last.emit({ type: "status", status: "running" });
  await userEvent.click(await screen.findByRole("button", { name: "中止" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/analysis/r2/abort", expect.objectContaining({ method: "POST" })));
});
