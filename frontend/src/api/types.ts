export interface Health { status: string; model?: string; provider?: string; }
export interface StartAnalysisRequest {
  ticker: string; trade_date: string; config_overrides: Record<string, unknown>;
}
export interface StartAnalysisResponse { run_id: string; }

export interface Quote {
  name: string;
  price: number | string | null;
  change: number | string | null;
  changePercent: number | string | null;
}
export interface AbortResponse { run_id: string; accepted: boolean; }

export interface TokenStats {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cached_input_tokens?: number;
  uncached_input_tokens?: number;
  cost_usd: number;
  tool_calls: Record<string, number>;
  tool_call_count: number;
}

export interface CumulativeStats {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  tool_calls: number;
  runs: number;
}

export type WsEvent =
  | { type: "status"; status: string }
  | { type: "chunk"; payload: Record<string, unknown> & { __streaming?: Record<string, boolean>; __activity?: StreamActivity } }
  | { type: "done"; status: string; token_stats?: TokenStats }
  | { type: "aborted" }
  | { type: "error"; message: string }
  | { type: "ping" };

export interface StreamActivity {
  agent: string;
  kind: string;
}

export interface HistoryItem {
  id: number;
  ticker: string; trade_date: string;
  rating: string | null; summary: string | null;
  model: string | null; provider: string | null;
  has_position: string | null;
  note: string | null; user_rating: string | null;
  created_at: string; json_path: string;
  pdf_path: string | null;
}
export interface HistoryListResponse { items: HistoryItem[]; }
export interface PatchHistoryRequest { note?: string; rating?: string; }

export interface RunReportResponse {
  ticker: string;
  trade_date: string;
  final_state: Record<string, unknown>;
}

export interface DiffSection {
  title: string;
  changed: boolean;
  diff: string;
  a_text: string;
  b_text: string;
}
export interface DiffResponse {
  a: { ticker: string; trade_date: string };
  b: { ticker: string; trade_date: string };
  sections: Record<string, DiffSection>;
}

export interface DiagnosticsResponse { degraded: string[]; checked_at: string; }

export interface ProviderInfo {
  id: string; name: string;
  env_var: string | null; base_url: string | null; configured: boolean;
}
export interface AppSettings {
  results_dir: string;
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url: string;
}
export type UpdateSettings = Partial<AppSettings>;

export interface ProviderListResponse { providers: ProviderInfo[]; }
export interface SetKeyResponse { id: string; configured: boolean; }
export interface TestProviderResponse {
  id: string; ok: boolean; reason: string; status?: number | null;
}
