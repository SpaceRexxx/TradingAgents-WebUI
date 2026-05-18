import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import RunReportPage from "./RunReportPage";

beforeEach(() => vi.restoreAllMocks());

function renderPage(path = "/history/AAPL/2026-01-02") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/history/:ticker/:tradeDate" element={<RunReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("loads and renders a completed analysis report", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      ticker: "AAPL",
      trade_date: "2026-01-02",
      final_state: {
        market_report: "# Market\nstrong",
        investment_plan: "Hold with caution",
        final_trade_decision: "BUY",
        investment_debate_state: { bull_history: "Bull case" },
      },
    }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);

  renderPage();

  await waitFor(() =>
    expect(f).toHaveBeenCalledWith(
      "/api/runs/AAPL/2026-01-02/report",
      expect.objectContaining({ method: "GET" }),
    ),
  );
  expect(await screen.findByRole("heading", { name: "AAPL 完整分析报告" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Market" })).toBeInTheDocument();
  expect(screen.getByText("Hold with caution")).toBeInTheDocument();
  expect(screen.getByText("Bull case")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "下载 PDF" }))
    .toHaveAttribute("href", "/api/runs/AAPL/2026-01-02/pdf");
});

it("shows an error when the report is missing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: async () => ({ detail: "not found" }),
  } as unknown as Response));

  renderPage();

  expect(await screen.findByText(/加载报告失败: 404/)).toBeInTheDocument();
});
