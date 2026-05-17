import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import AnalysisPage from "./AnalysisPage";

class FakeWS {
  static last: FakeWS;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number; reason: string; wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeWS.last = this; }
  send() {}
  close() { this.closed = true; this.onclose?.({ code: 1000, reason: "", wasClean: true }); }
  emit(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

beforeEach(() => {
  vi.restoreAllMocks();
  try { localStorage.removeItem("ta_prefs"); } catch { /* node localStorage quirk */ }
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
});

it("start posts form with config_overrides, streams chunks into agent preview, reaches done", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r1" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);

  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("股票代码"), "AAPL");
  // 分析日期 defaults to today; no typing needed.
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));

  await waitFor(() => {
    const call = f.mock.calls.find((c) => c[0] === "/api/analysis/start");
    expect(call).toBeTruthy();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body.ticker).toBe("AAPL");
    expect(body.config_overrides.selected_analysts).toEqual([
      "market", "social", "news", "fundamentals",
    ]);
    expect(body.config_overrides.max_debate_rounds).toBe(2);
    expect(body.config_overrides.has_position).toBe("未持有");
  });
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r1"));

  FakeWS.last.emit({ type: "status", status: "running" });
  FakeWS.last.emit({ type: "chunk", payload: { market_report: "# Market\nstrong buy" } });
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Market" })).toBeInTheDocument());

  FakeWS.last.emit({
    type: "done",
    status: "done",
    token_stats: {
      input_tokens: 6110, output_tokens: 3975, total_tokens: 10085,
      cost_usd: 0.018, tool_calls: { get_news: 2 }, tool_call_count: 2,
    },
  });
  await waitFor(() => expect(screen.getByText(/已完成/)).toBeInTheDocument());
  expect(screen.getByText("本次分析透明度")).toBeInTheDocument();
  expect(screen.getByText("10,085")).toBeInTheDocument();
  expect(screen.getByText("$0.0180")).toBeInTheDocument();
  expect(screen.getByText(/数据新鲜度/)).toBeInTheDocument();
});

it("abort posts to the abort endpoint", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r2", accepted: true }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("股票代码"), "AAPL");
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));
  await waitFor(() => expect(FakeWS.last?.url).toContain("/ws/r2"));
  FakeWS.last.emit({ type: "status", status: "running" });
  await userEvent.click(await screen.findByRole("button", { name: "中止" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/analysis/r2/abort", expect.objectContaining({ method: "POST" })));
});

it("deselecting all analysts blocks start", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ run_id: "r3" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<AnalysisPage />);
  await userEvent.type(screen.getByLabelText("股票代码"), "AAPL");
  for (const label of ["市场分析师", "舆情分析师", "新闻分析师", "基本面分析师"]) {
    await userEvent.click(screen.getByLabelText(label));
  }
  await userEvent.click(screen.getByRole("button", { name: "开始分析" }));
  expect(f.mock.calls.find((c) => c[0] === "/api/analysis/start")).toBeFalsy();
});
