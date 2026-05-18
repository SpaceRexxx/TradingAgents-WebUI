import { useEffect, useMemo, useRef, useState } from "react";
import { startAnalysis, abortAnalysis, pdfUrl, getQuote } from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import { usePrefs } from "../hooks/usePrefs";
import { deriveProgress, type AgentStatus } from "../util/progress";
import Markdown from "../components/Markdown";
import StatCard, { fmtInt, fmtCost } from "../components/StatCard";
import { useAppStore } from "../store/appStore";
import type { Quote } from "../api/types";

const ANALYSTS: { key: string; label: string }[] = [
  { key: "market", label: "市场分析师" },
  { key: "social", label: "舆情分析师" },
  { key: "news", label: "新闻分析师" },
  { key: "fundamentals", label: "基本面分析师" },
];

const DEPTHS: { value: number; label: string }[] = [
  { value: 0, label: "极浅" },
  { value: 1, label: "浅层" },
  { value: 2, label: "中等" },
  { value: 3, label: "深入" },
];

const today = () => new Date().toISOString().slice(0, 10);

function statusIcon(s: AgentStatus): string {
  return s === "done" ? "✅" : s === "running" ? "⏳" : "⚪";
}

function fmtElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`;
}

function age(ts: number | null): string {
  if (!ts) return "尚无";
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  return fmtElapsed(sec);
}

function activityKind(kind?: string): string {
  return kind === "thinking" ? "模型思考中" : kind === "started" ? "已开始调用模型" : "有活动";
}

function closeSummary(code: number, reason: string, wasClean: boolean): string {
  const label = wasClean ? "正常关闭" : "异常关闭";
  return reason ? `${label} ${code}: ${reason}` : `${label} ${code}`;
}

function num(v: unknown): string {
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

function freshness(tradeDate: string): string {
  const t = Date.parse(tradeDate);
  if (Number.isNaN(t)) return "";
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days <= 0) return "数据新鲜度：当日实时";
  if (days <= 3) return `数据新鲜度：${days} 天前 · 近期数据`;
  return `数据新鲜度：${days} 天前 · 历史回顾`;
}

export default function AnalysisPage() {
  const [ticker, setTicker] = useState("");
  const [tradeDate, setTradeDate] = useState(today());
  const [runId, setRunId] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);

  const [prefs, setPrefs] = usePrefs();
  const stream = useAnalysisStream();
  const pushToast = useAppStore((s) => s.pushToast);

  const running = stream.status === "running";
  const progress = useMemo(
    () => deriveProgress(stream.report, running),
    [stream.report, running],
  );

  // Elapsed-time ticker: runs while the stream is running.
  useEffect(() => {
    if (running) {
      if (startedAt.current === null) startedAt.current = Date.now();
      const id = setInterval(() => {
        setElapsed(Math.floor((Date.now() - (startedAt.current ?? Date.now())) / 1000));
      }, 1000);
      return () => clearInterval(id);
    }
  }, [running]);

  // Default the preview to the first running (or first completed) agent.
  useEffect(() => {
    if (selectedAgent) return;
    const active =
      progress.agents.find((a) => a.status === "running" && a.content) ||
      progress.agents.find((a) => a.content);
    if (active) setSelectedAgent(active.key);
  }, [progress.agents, selectedAgent]);

  const fetchQuote = async () => {
    const t = ticker.trim();
    if (!t) {
      setQuote(null);
      return;
    }
    try {
      setQuote(await getQuote(t));
    } catch {
      setQuote(null);
    }
  };

  const start = async () => {
    if (prefs.selectedAnalysts.length === 0) {
      pushToast("err", "请至少选择一位分析师");
      return;
    }
    startedAt.current = null;
    setElapsed(0);
    setSelectedAgent(null);
    const config_overrides = {
      selected_analysts: prefs.selectedAnalysts,
      max_debate_rounds: prefs.researchDepth,
      max_risk_discuss_rounds: prefs.researchDepth,
      lookback_days: prefs.lookbackDays,
      news_lookback_days: prefs.newsLookbackDays,
      has_position: prefs.hasPosition ? "已持有" : "未持有",
    };
    try {
      const { run_id } = await startAnalysis({ ticker, trade_date: tradeDate, config_overrides });
      setRunId(run_id);
      stream.connect(run_id);
    } catch (e: any) {
      pushToast("err", `启动失败: ${e.status ?? e}`);
    }
  };

  const abort = async () => {
    if (!runId) return;
    try {
      await abortAnalysis(runId);
    } catch (e: any) {
      pushToast("err", `中止失败: ${e.status ?? e}`);
    }
  };

  const toggleAnalyst = (key: string) => {
    const next = prefs.selectedAnalysts.includes(key)
      ? prefs.selectedAnalysts.filter((k) => k !== key)
      : [...prefs.selectedAnalysts, key];
    setPrefs({ selectedAnalysts: next });
  };

  const quoteUp =
    quote && typeof quote.change === "number" ? quote.change >= 0 : true;
  const active = progress.agents.find((a) => a.key === selectedAgent);
  const activeActivity =
    active && stream.lastActivity?.agent === active.key ? stream.lastActivity : null;
  const stale = running && stream.lastEventAt !== null && Date.now() - stream.lastEventAt > 90000;
  const noHeartbeat = stale && stream.pingCount === 0;
  const staleReason = noHeartbeat
    ? "超过 90 秒无后端消息且未收到心跳，优先检查 WebSocket 或后端连接"
    : "超过 90 秒无后端消息，可能卡住或网络断开";

  return (
    <div className="col">
      <h2>分析中心</h2>

      {/* ── Row 1: ticker + price + position + start ─────────────── */}
      <div className="card col" style={{ gap: "var(--sp-3)" }}>
        <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="col" style={{ gap: 4, flex: 1, minWidth: 200 }}>
            股票代码
            <input
              aria-label="股票代码"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              onBlur={fetchQuote}
            />
          </label>
          <label className="col" style={{ gap: 4 }}>
            分析日期
            <input
              aria-label="分析日期"
              type="date"
              max={today()}
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
            />
          </label>
          <label className="row" style={{ gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              aria-label="已持有仓位"
              checked={prefs.hasPosition}
              onChange={(e) => setPrefs({ hasPosition: e.target.checked })}
            />
            已持有仓位
          </label>
          <button className="btn" disabled={running || !ticker || !tradeDate} onClick={start}>
            开始分析
          </button>
          {running && (
            <button className="btn-ghost" onClick={abort}>
              中止
            </button>
          )}
        </div>

        {quote && (
          <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
            <strong>{quote.name || ticker}</strong>
            <span style={{ fontWeight: 700 }}>{num(quote.price)}</span>
            <span style={{ color: quoteUp ? "var(--c-ok)" : "var(--c-err)" }}>
              {quoteUp ? "↑" : "↓"} {num(quote.changePercent)}
            </span>
          </div>
        )}
      </div>

      {/* ── Row 2: analysts + research depth ─────────────────────── */}
      <div className="card row" style={{ flexWrap: "wrap", gap: "var(--sp-6)" }}>
        <div className="col" style={{ gap: 6 }}>
          <span style={{ color: "var(--c-text-dim)" }}>分析师</span>
          <div className="row" style={{ flexWrap: "wrap", gap: "var(--sp-4)" }}>
            {ANALYSTS.map((a) => (
              <label key={a.key} className="row" style={{ gap: 6 }}>
                <input
                  type="checkbox"
                  aria-label={a.label}
                  checked={prefs.selectedAnalysts.includes(a.key)}
                  onChange={() => toggleAnalyst(a.key)}
                />
                {a.label}
              </label>
            ))}
          </div>
        </div>
        <div className="col" style={{ gap: 6 }}>
          <span style={{ color: "var(--c-text-dim)" }}>研究深度</span>
          <div className="row" style={{ gap: "var(--sp-4)" }}>
            {DEPTHS.map((d) => (
              <label key={d.value} className="row" style={{ gap: 6 }}>
                <input
                  type="radio"
                  name="depth"
                  aria-label={d.label}
                  checked={prefs.researchDepth === d.value}
                  onChange={() => setPrefs({ researchDepth: d.value })}
                />
                {d.label}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 3: lookback sliders ──────────────────────────────── */}
      <div className="card row" style={{ flexWrap: "wrap", gap: "var(--sp-6)" }}>
        <label className="col" style={{ gap: 4, flex: 1, minWidth: 220 }}>
          价格回溯 (天): {prefs.lookbackDays}
          <input
            type="range"
            aria-label="价格回溯 (天)"
            min={5}
            max={120}
            value={prefs.lookbackDays}
            onChange={(e) => setPrefs({ lookbackDays: Number(e.target.value) })}
          />
        </label>
        <label className="col" style={{ gap: 4, flex: 1, minWidth: 220 }}>
          新闻回溯 (天): {prefs.newsLookbackDays}
          <input
            type="range"
            aria-label="新闻回溯 (天)"
            min={1}
            max={30}
            value={prefs.newsLookbackDays}
            onChange={(e) => setPrefs({ newsLookbackDays: Number(e.target.value) })}
          />
        </label>
      </div>

      {/* ── Progress stepper + elapsed ───────────────────────────── */}
      {stream.status !== "idle" && (
        <div className="card col" style={{ gap: "var(--sp-3)" }}>
          <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
            <div className="row" style={{ gap: "var(--sp-4)", flexWrap: "wrap" }}>
              {progress.phases.map((p) => (
                <span
                  key={p.key}
                  style={{
                    color:
                      p.status === "done"
                        ? "var(--c-ok)"
                        : p.status === "running"
                        ? "var(--c-accent)"
                        : "var(--c-text-dim)",
                    fontWeight: p.status === "running" ? 700 : 400,
                  }}
                >
                  {statusIcon(p.status)} {p.label}
                </span>
              ))}
            </div>
            <span style={{ color: "var(--c-text-dim)" }}>
              已耗时 {fmtElapsed(elapsed)} ·{" "}
              {stream.status === "running"
                ? `分析中 (${progress.percent}%)`
                : stream.status === "done"
                ? "已完成"
                : stream.status === "aborted"
                ? "已中止"
                : `错误: ${stream.error}`}
            </span>
          </div>
          {running && (
            <div className="row" style={{ gap: "var(--sp-4)", flexWrap: "wrap", color: stale ? "var(--c-warn)" : "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
              <span>最近消息：{age(stream.lastEventAt)}前</span>
              <span>最近正文：{age(stream.lastChunkAt)}前</span>
              <span>心跳：{stream.pingCount > 0 ? `${age(stream.lastPingAt)}前` : "等待中"}</span>
              <span>事件：{stream.chunkCount}</span>
              {stream.lastClose && (
                <span>
                  连接：{closeSummary(stream.lastClose.code, stream.lastClose.reason, stream.lastClose.wasClean)}
                </span>
              )}
              {stream.lastActivity && (
                <span>
                  {progress.agents.find((a) => a.key === stream.lastActivity?.agent)?.label ?? stream.lastActivity.agent}
                  ：{activityKind(stream.lastActivity.kind)}
                </span>
              )}
              {stale && <span>{staleReason}</span>}
            </div>
          )}
          <div
            style={{
              height: 6,
              background: "var(--c-surface-2)",
              borderRadius: 4,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progress.percent}%`,
                height: "100%",
                background: "var(--c-accent)",
                transition: "width .3s",
              }}
            />
          </div>
        </div>
      )}

      {/* ── Agent sidebar + preview ──────────────────────────────── */}
      {stream.status !== "idle" && (
        <div className="row" style={{ alignItems: "flex-start", gap: "var(--sp-4)" }}>
          <div className="card col" style={{ gap: 4, minWidth: 180 }}>
            {progress.agents.map((a) => (
              <button
                key={a.key}
                onClick={() => setSelectedAgent(a.key)}
                className="btn-ghost"
                aria-label={a.label}
                style={{
                  textAlign: "left",
                  border: 0,
                  background: a.key === selectedAgent ? "var(--c-surface-2)" : "transparent",
                  fontWeight: a.key === selectedAgent ? 700 : 400,
                }}
              >
                {statusIcon(a.status)} {a.label}
              </button>
            ))}
          </div>
          <div className="card" style={{ flex: 1, minWidth: 0 }}>
            {active && active.content ? (
              <>
                <h3>{active.label}</h3>
                <Markdown>{active.content}</Markdown>
              </>
            ) : (
              <div className="col" style={{ gap: 6, color: "var(--c-text-dim)" }}>
                <span>
                  {active
                    ? `${active.label} · ${
                        activeActivity
                          ? activityKind(activeActivity.kind)
                          : active.status === "running"
                          ? "正在执行中"
                          : "暂无内容"
                      }`
                    : "等待分析开始…"}
                </span>
                {running && (
                  <span style={{ fontSize: "var(--fz-sm)" }}>
                    最近消息 {age(stream.lastEventAt)}前 · 最近正文 {age(stream.lastChunkAt)}前 · 心跳 {stream.pingCount > 0 ? `${age(stream.lastPingAt)}前` : "等待中"}
                    {stream.lastClose
                      ? ` · 连接 ${closeSummary(stream.lastClose.code, stream.lastClose.reason, stream.lastClose.wasClean)}`
                      : ""}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {stream.status === "done" && stream.tokenStats && (
        <StatCard
          title="本次分析透明度"
          metrics={[
            { label: "输入 tokens", value: fmtInt(stream.tokenStats.input_tokens) },
            ...(stream.tokenStats.cached_input_tokens || stream.tokenStats.uncached_input_tokens
              ? [
                  { label: "缓存输入", value: fmtInt(stream.tokenStats.cached_input_tokens ?? 0) },
                  { label: "非缓存输入", value: fmtInt(stream.tokenStats.uncached_input_tokens ?? 0) },
                ]
              : []),
            { label: "输出 tokens", value: fmtInt(stream.tokenStats.output_tokens) },
            { label: "总 tokens", value: fmtInt(stream.tokenStats.total_tokens) },
            { label: "估算成本 (USD)", value: fmtCost(stream.tokenStats.cost_usd) },
            { label: "工具调用次数", value: fmtInt(stream.tokenStats.tool_call_count) },
          ]}
          footer={
            <div className="col" style={{ gap: 2 }}>
              {Object.keys(stream.tokenStats.tool_calls).length > 0 && (
                <span>
                  📡 数据源调用：
                  {Object.entries(stream.tokenStats.tool_calls)
                    .sort((a, b) => b[1] - a[1])
                    .map(([n, c]) => `${n}×${c}`)
                    .join(" · ")}
                </span>
              )}
              <span>📅 {freshness(tradeDate)}</span>
            </div>
          }
        />
      )}

      {stream.status === "done" && runId && ticker && tradeDate && (
        <a
          className="btn-ghost"
          href={pdfUrl(ticker, tradeDate)}
          target="_blank"
          rel="noreferrer"
          style={{
            textDecoration: "none",
            padding: "var(--sp-2) var(--sp-4)",
            width: "fit-content",
          }}
        >
          下载本次 PDF
        </a>
      )}
    </div>
  );
}
