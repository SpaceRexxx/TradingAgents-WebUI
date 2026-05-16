import { useState } from "react";
import { startAnalysis, abortAnalysis, pdfUrl } from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import Markdown from "../components/Markdown";
import { useAppStore } from "../store/appStore";

const REPORT_KEYS: { key: string; label: string }[] = [
  { key: "market_report", label: "市场分析" },
  { key: "sentiment_report", label: "社交情绪" },
  { key: "news_report", label: "新闻分析" },
  { key: "fundamentals_report", label: "基本面" },
  { key: "investment_plan", label: "研究决策" },
  { key: "trader_investment_plan", label: "交易计划" },
  { key: "final_trade_decision", label: "最终决策" },
];

export default function AnalysisPage() {
  const [ticker, setTicker] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const stream = useAnalysisStream();
  const pushToast = useAppStore((s) => s.pushToast);

  const start = async () => {
    try {
      const { run_id } = await startAnalysis({ ticker, trade_date: tradeDate, config_overrides: {} });
      setRunId(run_id);
      stream.connect(run_id);
    } catch (e: any) {
      pushToast("err", `启动失败: ${e.status ?? e}`);
    }
  };

  const abort = async () => {
    if (!runId) return;
    try { await abortAnalysis(runId); } catch (e: any) { pushToast("err", `中止失败: ${e.status ?? e}`); }
  };

  const running = stream.status === "running";

  return (
    <div className="col">
      <h2>分析中心</h2>
      <div className="card row" style={{ flexWrap: "wrap" }}>
        <label className="col" style={{ gap: 4 }}>
          Ticker
          <input aria-label="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </label>
        <label className="col" style={{ gap: 4 }}>
          交易日期
          <input aria-label="交易日期" placeholder="YYYY-MM-DD" value={tradeDate}
            onChange={(e) => setTradeDate(e.target.value)} />
        </label>
        <button className="btn" disabled={running || !ticker || !tradeDate} onClick={start}>开始分析</button>
        {running && <button className="btn-ghost" onClick={abort}>中止</button>}
        <span style={{ color: "var(--c-text-dim)" }}>
          状态:{" "}
          {stream.status === "idle" ? "待命"
            : stream.status === "running" ? `分析中 (${stream.chunkCount} chunk)`
            : stream.status === "done" ? "已完成"
            : stream.status === "aborted" ? "已中止"
            : `错误: ${stream.error}`}
        </span>
      </div>

      {REPORT_KEYS.map(({ key, label }) => {
        const raw = stream.report[key];
        const val = typeof raw === "string" ? raw : undefined;
        if (!val) return null;
        return (
          <div key={key} className="card">
            <h3>{label}</h3>
            <Markdown>{val}</Markdown>
          </div>
        );
      })}

      {stream.status === "done" && runId && ticker && tradeDate && (
        <a className="btn-ghost" href={pdfUrl(ticker, tradeDate)} target="_blank" rel="noreferrer"
           style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)", width: "fit-content" }}>
          下载本次 PDF
        </a>
      )}
    </div>
  );
}
