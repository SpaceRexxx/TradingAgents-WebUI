import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import HistoryPage from "./HistoryPage";

const ITEM = {
  ticker: "AAPL", trade_date: "2026-01-02", rating: "Buy",
  summary: "strong", model: "deepseek", provider: "DeepSeek",
  note: null, user_rating: null, created_at: "2026-01-02T10:00:00Z",
  json_path: "/x/AAPL/2026-01-02/final_state_report.json",
};

beforeEach(() => vi.restoreAllMocks());

function fetchMock(handler: (url: string, init?: RequestInit) => unknown) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true, status: 200, json: async () => handler(url, init),
  } as unknown as Response));
}

it("renders history rows", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ items: [ITEM] })));
  render(<HistoryPage />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "AAPL 2026-01-02" })).toBeInTheDocument());
  expect(screen.getByText("Buy")).toBeInTheDocument();
});

it("filters by ticker", async () => {
  const f = fetchMock(() => ({ items: [ITEM] }));
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  await userEvent.type(screen.getByPlaceholderText("按 ticker 过滤"), "AAPL");
  await userEvent.click(screen.getByRole("button", { name: "查询" }));
  await waitFor(() =>
    expect(f).toHaveBeenLastCalledWith("/api/history?ticker=AAPL", expect.objectContaining({ method: "GET" })));
});

it("saves a note via PATCH", async () => {
  const f = fetchMock((_url, init) =>
    init?.method === "PATCH" ? { ticker: "AAPL", trade_date: "2026-01-02", updated: true } : { items: [ITEM] });
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  await userEvent.click(screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  await userEvent.type(await screen.findByPlaceholderText("备注"), "looks good");
  await userEvent.click(screen.getByRole("button", { name: "保存备注" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-02",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ note: "looks good" }) })));
});

it("PDF link points at the runs endpoint", async () => {
  vi.stubGlobal("fetch", fetchMock(() => ({ items: [ITEM] })));
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  await userEvent.click(screen.getByRole("button", { name: "AAPL 2026-01-02" }));
  expect(await screen.findByRole("link", { name: "下载 PDF" }))
    .toHaveAttribute("href", "/api/runs/AAPL/2026-01-02/pdf");
});

const ITEM_A = {
  ticker: "AAPL", trade_date: "2026-01-01", rating: "Buy",
  summary: "first", model: "deepseek", provider: "DeepSeek",
  note: null, user_rating: null, created_at: "2026-01-01T10:00:00Z",
  json_path: "/x/AAPL/2026-01-01/final_state_report.json",
};
const ITEM_B = {
  ticker: "AAPL", trade_date: "2026-02-01", rating: "Sell",
  summary: "second", model: "deepseek", provider: "DeepSeek",
  note: null, user_rating: null, created_at: "2026-02-01T10:00:00Z",
  json_path: "/x/AAPL/2026-02-01/final_state_report.json",
};
const DIFF_RESP = {
  a: { ticker: "AAPL", trade_date: "2026-01-01" },
  b: { ticker: "AAPL", trade_date: "2026-02-01" },
  sections: {
    final_trade_decision: { changed: true, diff: "- BUY\n+ SELL" },
    market_report: { changed: false, diff: "" },
  },
};

it("compares two runs", async () => {
  const f = vi.fn().mockImplementation(async (url: string, _init?: RequestInit) => {
    if (url.includes("/diff/")) {
      return { ok: true, status: 200, json: async () => DIFF_RESP } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => ({ items: [ITEM_A, ITEM_B] }) } as unknown as Response;
  });
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "AAPL 2026-01-01" }));

  // Select A and B
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "对比 A" }), "AAPL|2026-01-01");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "对比 B" }), "AAPL|2026-02-01");
  await userEvent.click(screen.getByRole("button", { name: "对比" }));

  await waitFor(() =>
    expect(f).toHaveBeenCalledWith(
      "/api/history/AAPL/2026-01-01/diff/AAPL/2026-02-01",
      expect.objectContaining({ method: "GET" })
    )
  );

  expect(await screen.findByText("final_trade_decision")).toBeInTheDocument();
  expect(screen.getByText(/- BUY/)).toBeInTheDocument();
  expect(screen.getByText(/\+ SELL/)).toBeInTheDocument();
  expect(screen.getByText("无变更")).toBeInTheDocument();
});

it("diff 404 toasts an error", async () => {
  const f = vi.fn().mockImplementation(async (url: string, _init?: RequestInit) => {
    if (url.includes("/diff/")) {
      return { ok: false, status: 404, json: async () => ({ detail: "not found" }) } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => ({ items: [ITEM_A, ITEM_B] }) } as unknown as Response;
  });
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "AAPL 2026-01-01" }));

  await userEvent.selectOptions(screen.getByRole("combobox", { name: "对比 A" }), "AAPL|2026-01-01");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "对比 B" }), "AAPL|2026-02-01");
  await userEvent.click(screen.getByRole("button", { name: "对比" }));

  await waitFor(() =>
    expect(f).toHaveBeenCalledWith(
      "/api/history/AAPL/2026-01-01/diff/AAPL/2026-02-01",
      expect.objectContaining({ method: "GET" })
    )
  );

  // No diff panel should appear
  expect(screen.queryByText("final_trade_decision")).toBeNull();
});

// --- NEW TESTS: loading / empty / error states ---

it("shows empty state when fetch resolves with no items", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ items: [] }),
  } as unknown as Response));
  render(<HistoryPage />);
  await waitFor(() => expect(screen.getByText("暂无历史分析记录。")).toBeInTheDocument());
});

it("shows inline error and retry button on initial load failure", async () => {
  const f = vi.fn().mockRejectedValueOnce({ status: 500 });
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => expect(screen.getByText("加载失败，请重试。")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
});

it("renders the cumulative stats card", async () => {
  vi.stubGlobal("fetch", fetchMock((url) =>
    url.includes("/api/stats/cumulative")
      ? { input_tokens: 32864, output_tokens: 22619, total_tokens: 53353,
          cost_usd: 0.1007, tool_calls: 0, runs: 15 }
      : { items: [ITEM] }));
  render(<HistoryPage />);
  await waitFor(() =>
    expect(screen.getByText("累计统计（所有分析）")).toBeInTheDocument());
  expect(screen.getByText("53,353")).toBeInTheDocument();
  expect(screen.getByText("$0.1007")).toBeInTheDocument();
  expect(screen.getByText(/15 次分析累计/)).toBeInTheDocument();
});

it("retry button re-calls /api/history", async () => {
  const f = vi.fn()
    .mockRejectedValueOnce({ status: 500 })
    .mockResolvedValue({
      ok: true, status: 200, json: async () => ({ items: [] }),
    } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<HistoryPage />);
  await waitFor(() => screen.getByRole("button", { name: "重试" }));
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/history", expect.objectContaining({ method: "GET" })));
});
