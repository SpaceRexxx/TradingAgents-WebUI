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

it("renders structured decision table and compliance footer", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      ticker: "AAPL",
      trade_date: "2026-01-02",
      final_state: {
        market_report: "# M\nx",
        portfolio_decision: {
          rating: "Buy", conviction_score: 8,
          executive_summary: "建仓 250-255", investment_thesis: "多头更强",
          stop_loss: 240, time_horizon: "1-3 个月",
        },
        run_meta: {
          generated_at: "2026-01-02T03:04:05Z", model: "deepseek-v4-pro",
          provider: "DeepSeek", tokens: { total_tokens: 1234, cost_usd: 0.05 },
          disclaimer: "本报告由 AI 多智能体系统自动生成,不构成任何投资建议。",
        },
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
  expect(await screen.findByText("建仓 250-255")).toBeInTheDocument();
  expect(screen.getByText("Buy")).toBeInTheDocument();
  expect(screen.getByText("8/10")).toBeInTheDocument();
  expect(screen.getByText(/不构成任何投资建议/)).toBeInTheDocument();
  expect(screen.getByText(/deepseek-v4-pro/)).toBeInTheDocument();
});
