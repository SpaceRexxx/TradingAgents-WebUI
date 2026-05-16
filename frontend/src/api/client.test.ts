import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response);
}

beforeEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("getHealth GETs /api/health", async () => {
    const f = mockFetch(200, { status: "ok" });
    vi.stubGlobal("fetch", f);
    expect(await api.getHealth()).toEqual({ status: "ok" });
    expect(f).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
  });

  it("startAnalysis POSTs body", async () => {
    const f = mockFetch(200, { run_id: "abc123" });
    vi.stubGlobal("fetch", f);
    const r = await api.startAnalysis({ ticker: "AAPL", trade_date: "2026-01-02", config_overrides: {} });
    expect(f).toHaveBeenCalledWith("/api/analysis/start", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: "AAPL", trade_date: "2026-01-02", config_overrides: {} }),
    }));
    expect(r.run_id).toBe("abc123");
  });

  it("abortAnalysis POSTs to /{id}/abort", async () => {
    const f = mockFetch(200, { run_id: "x", accepted: true });
    vi.stubGlobal("fetch", f);
    await api.abortAnalysis("x");
    expect(f).toHaveBeenCalledWith("/api/analysis/x/abort", expect.objectContaining({ method: "POST" }));
  });

  it("listHistory with and without ticker", async () => {
    const f = mockFetch(200, { items: [] });
    vi.stubGlobal("fetch", f);
    await api.listHistory("AAPL");
    await api.listHistory();
    expect(f).toHaveBeenNthCalledWith(1, "/api/history?ticker=AAPL", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/history", expect.objectContaining({ method: "GET" }));
  });

  it("patchHistory PATCHes", async () => {
    const f = mockFetch(200, { ticker: "AAPL", trade_date: "2026-01-02", updated: true });
    vi.stubGlobal("fetch", f);
    await api.patchHistory("AAPL", "2026-01-02", { note: "hi" });
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-02",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ note: "hi" }) }));
  });

  it("getDiff GETs the diff path", async () => {
    const f = mockFetch(200, { a: {}, b: {}, sections: {} });
    vi.stubGlobal("fetch", f);
    await api.getDiff("AAPL", "2026-01-01", "AAPL", "2026-02-01");
    expect(f).toHaveBeenCalledWith("/api/history/AAPL/2026-01-01/diff/AAPL/2026-02-01",
      expect.objectContaining({ method: "GET" }));
  });

  it("diagnostics get + run", async () => {
    const f = mockFetch(200, { degraded: [], checked_at: "t" });
    vi.stubGlobal("fetch", f);
    await api.getDiagnostics();
    await api.runDiagnostics();
    expect(f).toHaveBeenNthCalledWith(1, "/api/diagnostics", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/diagnostics/run", expect.objectContaining({ method: "POST" }));
  });

  it("providers list/setkey/test", async () => {
    const f = mockFetch(200, { providers: [] });
    vi.stubGlobal("fetch", f);
    await api.listProviders();
    await api.setProviderKey("deepseek", "sk-x");
    await api.testProvider("deepseek");
    expect(f).toHaveBeenNthCalledWith(1, "/api/providers", expect.objectContaining({ method: "GET" }));
    expect(f).toHaveBeenNthCalledWith(2, "/api/providers/deepseek/key",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ api_key: "sk-x" }) }));
    expect(f).toHaveBeenNthCalledWith(3, "/api/providers/deepseek/test",
      expect.objectContaining({ method: "POST" }));
  });

  it("pdfUrl builds the path (no fetch)", () => {
    expect(api.pdfUrl("AAPL", "2026-01-02")).toBe("/api/runs/AAPL/2026-01-02/pdf");
  });

  it("throws ApiError with status + detail on non-2xx", async () => {
    const f = mockFetch(404, { detail: "nope" });
    vi.stubGlobal("fetch", f);
    await expect(api.listHistory("X")).rejects.toMatchObject({ status: 404, detail: "nope" });
  });
});
