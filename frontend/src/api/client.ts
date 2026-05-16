import type {
  Health, StartAnalysisRequest, StartAnalysisResponse, AbortResponse,
  HistoryListResponse, PatchHistoryRequest, DiffResponse,
  DiagnosticsResponse, ProviderListResponse, SetKeyResponse, TestProviderResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function req<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, { method: "GET", ...init });
  if (!resp.ok) {
    let detail: unknown = null;
    try { detail = (await resp.json())?.detail ?? null; } catch { /* non-JSON */ }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const getHealth = () => req<Health>("/api/health", { method: "GET" });

export const startAnalysis = (b: StartAnalysisRequest) =>
  req<StartAnalysisResponse>("/api/analysis/start", jsonBody("POST", b));

export const abortAnalysis = (runId: string) =>
  req<AbortResponse>(`/api/analysis/${encodeURIComponent(runId)}/abort`, { method: "POST" });

export const listHistory = (ticker?: string) =>
  req<HistoryListResponse>(
    ticker ? `/api/history?ticker=${encodeURIComponent(ticker)}` : "/api/history",
    { method: "GET" }
  );

export const patchHistory = (ticker: string, tradeDate: string, b: PatchHistoryRequest) =>
  req<{ ticker: string; trade_date: string; updated: boolean }>(
    `/api/history/${encodeURIComponent(ticker)}/${encodeURIComponent(tradeDate)}`,
    jsonBody("PATCH", b)
  );

export const getDiff = (t1: string, d1: string, t2: string, d2: string) =>
  req<DiffResponse>(
    `/api/history/${encodeURIComponent(t1)}/${encodeURIComponent(d1)}/diff/${encodeURIComponent(t2)}/${encodeURIComponent(d2)}`,
    { method: "GET" }
  );

export const getDiagnostics = () => req<DiagnosticsResponse>("/api/diagnostics", { method: "GET" });
export const runDiagnostics = () => req<DiagnosticsResponse>("/api/diagnostics/run", { method: "POST" });

export const listProviders = () => req<ProviderListResponse>("/api/providers", { method: "GET" });
export const setProviderKey = (id: string, apiKey: string) =>
  req<SetKeyResponse>(`/api/providers/${encodeURIComponent(id)}/key`, jsonBody("POST", { api_key: apiKey }));
export const testProvider = (id: string) =>
  req<TestProviderResponse>(`/api/providers/${encodeURIComponent(id)}/test`, { method: "POST" });

export const pdfUrl = (ticker: string, tradeDate: string) =>
  `/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(tradeDate)}/pdf`;
