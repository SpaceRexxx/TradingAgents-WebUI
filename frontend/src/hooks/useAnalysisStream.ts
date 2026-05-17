import { useCallback, useReducer, useRef } from "react";
import type { WsEvent, TokenStats, StreamActivity } from "../api/types";

export type StreamStatus = "idle" | "running" | "done" | "aborted" | "error";

export interface StreamCloseInfo {
  code: number;
  reason: string;
  wasClean: boolean;
}

export interface StreamState {
  status: StreamStatus;
  report: Record<string, unknown>;
  error: string | null;
  chunkCount: number;
  pingCount: number;
  tokenStats: TokenStats | null;
  lastEventAt: number | null;
  lastChunkAt: number | null;
  lastPingAt: number | null;
  lastActivity: StreamActivity | null;
  lastClose: StreamCloseInfo | null;
  connect: (runId: string) => void;
  disconnect: () => void;
}

type StreamData = Omit<StreamState, "connect" | "disconnect">;

type StreamAction =
  | { type: "reset" }
  | { type: "connect_start"; now: number }
  | { type: "status"; status: StreamStatus }
  | { type: "chunk"; payload: Record<string, unknown> & { __activity?: StreamActivity }; now: number }
  | { type: "ping"; now: number }
  | { type: "done"; tokenStats?: TokenStats }
  | { type: "aborted" }
  | { type: "error"; message: string }
  | { type: "closed"; closeInfo: StreamCloseInfo; now: number; expected: boolean }
  | { type: "ws_error"; now: number };

function wsUrl(runId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/${encodeURIComponent(runId)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergeReport(
  current: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...current };
  for (const [key, value] of Object.entries(patch)) {
    if (isRecord(value) && isRecord(next[key])) {
      next[key] = mergeReport(next[key] as Record<string, unknown>, value);
    } else if (key === "__streaming" && isRecord(value) && isRecord(next[key])) {
      next[key] = { ...(next[key] as Record<string, unknown>), ...value };
    } else {
      next[key] = value;
    }
  }
  return next;
}

const initialState: StreamData = {
  status: "idle",
  report: {},
  error: null,
  chunkCount: 0,
  pingCount: 0,
  tokenStats: null,
  lastEventAt: null,
  lastChunkAt: null,
  lastPingAt: null,
  lastActivity: null,
  lastClose: null,
};

function reducer(state: StreamData, action: StreamAction): StreamData {
  switch (action.type) {
    case "reset":
      return initialState;
    case "connect_start":
      return {
        ...initialState,
        status: "running",
        lastEventAt: action.now,
      };
    case "status":
      return { ...state, status: action.status };
    case "chunk":
      return {
        ...state,
        report: mergeReport(state.report, action.payload),
        chunkCount: state.chunkCount + 1,
        lastEventAt: action.now,
        lastChunkAt: action.now,
        lastActivity: action.payload.__activity ?? state.lastActivity,
      };
    case "ping":
      return {
        ...state,
        pingCount: state.pingCount + 1,
        lastEventAt: action.now,
        lastPingAt: action.now,
      };
    case "done":
      return {
        ...state,
        status: "done",
        tokenStats: action.tokenStats ?? state.tokenStats,
      };
    case "aborted":
      return { ...state, status: "aborted" };
    case "error":
      return { ...state, status: "error", error: action.message };
    case "closed":
      if (action.expected) {
        return { ...state, lastEventAt: action.now, lastClose: action.closeInfo };
      }
      return {
        ...state,
        status: "error",
        error: `WebSocket closed unexpectedly (code ${action.closeInfo.code}${
          action.closeInfo.reason ? `, reason: ${action.closeInfo.reason}` : ""
        })`,
        lastEventAt: action.now,
        lastClose: action.closeInfo,
      };
    case "ws_error":
      return {
        ...state,
        status: "error",
        error: "WebSocket connection error",
        lastEventAt: action.now,
      };
  }
}

export function useAnalysisStream(): StreamState {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);
  const expectedCloseRef = useRef(false);

  const disconnect = useCallback(() => {
    expectedCloseRef.current = true;
    wsRef.current?.close();
    wsRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  const connect = useCallback((runId: string) => {
    expectedCloseRef.current = true;
    wsRef.current?.close();
    expectedCloseRef.current = false;
    dispatch({ type: "connect_start", now: Date.now() });
    const ws = new WebSocket(wsUrl(runId));
    wsRef.current = ws;
    ws.onmessage = (e: MessageEvent) => {
      if (wsRef.current !== ws) return;
      const now = Date.now();
      const ev = JSON.parse(e.data) as WsEvent;
      switch (ev.type) {
        case "status":
          dispatch({
            type: "status",
            status: ev.status === "running" ? "running" : (ev.status as StreamStatus),
          });
          break;
        case "chunk":
          dispatch({ type: "chunk", payload: ev.payload, now });
          break;
        case "done":
          dispatch({ type: "done", tokenStats: ev.token_stats });
          expectedCloseRef.current = true;
          ws.close();
          break;
        case "aborted":
          dispatch({ type: "aborted" });
          expectedCloseRef.current = true;
          ws.close();
          break;
        case "error":
          dispatch({ type: "error", message: ev.message });
          expectedCloseRef.current = true;
          ws.close();
          break;
        case "ping":
          dispatch({ type: "ping", now });
          break;
      }
    };
    ws.onclose = (event: CloseEvent) => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      const closeInfo = {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
      };
      dispatch({
        type: "closed",
        closeInfo,
        now: Date.now(),
        expected: expectedCloseRef.current,
      });
    };
    ws.onerror = () => {
      if (wsRef.current !== ws) return;
      dispatch({ type: "ws_error", now: Date.now() });
    };
  }, []);

  return {
    ...state,
    connect,
    disconnect,
  };
}
