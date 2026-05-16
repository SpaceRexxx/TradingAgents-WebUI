import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, it, expect } from "vitest";
import DiagnosticsPage from "./DiagnosticsPage";

beforeEach(() => vi.restoreAllMocks());

it("lists degraded sources", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ degraded: ["akshare 未安装"], checked_at: "2026-01-01T00:00:00Z" }),
  } as unknown as Response));
  render(<DiagnosticsPage />);
  await waitFor(() => expect(screen.getByText("akshare 未安装")).toBeInTheDocument());
});

it("all-clear when empty", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ degraded: [], checked_at: "t" }),
  } as unknown as Response));
  render(<DiagnosticsPage />);
  await waitFor(() => expect(screen.getByText(/全部数据源正常/)).toBeInTheDocument());
});

it("re-run calls POST /api/diagnostics/run", async () => {
  const f = vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => ({ degraded: [], checked_at: "t" }),
  } as unknown as Response);
  vi.stubGlobal("fetch", f);
  render(<DiagnosticsPage />);
  await waitFor(() => screen.getByText(/全部数据源正常/));
  await userEvent.click(screen.getByRole("button", { name: "重新检测" }));
  await waitFor(() =>
    expect(f).toHaveBeenCalledWith("/api/diagnostics/run", expect.objectContaining({ method: "POST" })));
});
