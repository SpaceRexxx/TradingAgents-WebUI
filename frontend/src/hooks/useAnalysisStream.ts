import { useCallback, useRef, useState } from "react";
import type { WsEvent, TokenStats } from "../api/types";

export type StreamStatus = "idle" | "running" | "done" | "aborted" | "error";

export interface StreamState {
  status: StreamStatus;
  report: Record<string, unknown>;
  error: string | null;
  chunkCount: number;
  tokenStats: TokenStats | null;
  connect: (runId: string) => void;
  disconnect: () => void;
}

function wsUrl(runId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/${encodeURIComponent(runId)}`;
}

export function useAnalysisStream(): StreamState {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [report, setReport] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [chunkCount, setChunkCount] = useState(0);
  const [tokenStats, setTokenStats] = useState<TokenStats | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("idle");
    setReport({});
    setError(null);
    setChunkCount(0);
    setTokenStats(null);
  }, []);

  const connect = useCallback((runId: string) => {
    wsRef.current?.close();
    setStatus("running");
    setReport({});
    setError(null);
    setChunkCount(0);
    setTokenStats(null);
    const ws = new WebSocket(wsUrl(runId));
    wsRef.current = ws;
    ws.onmessage = (e: MessageEvent) => {
      const ev = JSON.parse(e.data) as WsEvent;
      switch (ev.type) {
        case "status":
          setStatus(ev.status === "running" ? "running" : (ev.status as StreamStatus));
          break;
        case "chunk":
          setReport((r) => ({ ...r, ...ev.payload }));
          setChunkCount((n) => n + 1);
          break;
        case "done":
          if (ev.token_stats) setTokenStats(ev.token_stats);
          setStatus("done"); ws.close(); break;
        case "aborted":
          setStatus("aborted"); ws.close(); break;
        case "error":
          setStatus("error"); setError(ev.message); ws.close(); break;
        case "ping":
          break;
      }
    };
    ws.onerror = () => { setStatus("error"); setError("WebSocket connection error"); };
  }, []);

  return { status, report, error, chunkCount, tokenStats, connect, disconnect };
}
