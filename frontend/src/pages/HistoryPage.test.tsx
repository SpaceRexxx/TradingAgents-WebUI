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
