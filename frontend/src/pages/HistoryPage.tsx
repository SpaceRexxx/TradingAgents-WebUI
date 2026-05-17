import { useEffect, useState, useCallback } from "react";
import {
  listHistory, patchHistory, pdfUrl, getDiff, getCumulativeStats, reindexHistory,
} from "../api/client";
import type { HistoryItem, DiffResponse, CumulativeStats } from "../api/types";
import StatCard, { fmtInt, fmtCost } from "../components/StatCard";
import { useAppStore } from "../store/appStore";

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState("");
  const [selA, setSelA] = useState("");
  const [selB, setSelB] = useState("");
  const [diffResult, setDiffResult] = useState<DiffResponse | null>(null);
  const [cum, setCum] = useState<CumulativeStats | null>(null);
  const pushToast = useAppStore((s) => s.pushToast);

  const load = useCallback((ticker?: string) => {
    setLoading(true);
    setErrored(false);
    listHistory(ticker || undefined)
      .then((r) => { setItems(r.items); })
      .catch((e) => { setErrored(true); pushToast("err", `加载历史失败: ${e.status ?? e}`); })
      .finally(() => setLoading(false));
  }, [pushToast]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    getCumulativeStats().then(setCum).catch(() => setCum(null));
  }, []);

  const open = (it: HistoryItem) => {
    setSelected(it);
    setNote(it.note ?? "");
    setRating(it.user_rating ?? "");
  };

  const save = async () => {
    if (!selected) return;
    try {
      const body: { note?: string; rating?: string } = {};
      if (note) body.note = note;
      if (rating) body.rating = rating;
      await patchHistory(selected.ticker, selected.trade_date, body);
      pushToast("ok", "已保存");
      load(filter || undefined);
    } catch (e: any) {
      pushToast("err", `保存失败: ${e.status ?? e}`);
    }
  };

  const reindex = async () => {
    try {
      const r = await reindexHistory();
      pushToast("ok", `重建索引完成：恢复 ${r.recovered}，新增 ${r.indexed}`);
      load(filter || undefined);
      getCumulativeStats().then(setCum).catch(() => {});
    } catch (e: any) {
      pushToast("err", `重建索引失败: ${e.status ?? e}`);
    }
  };

  const compare = async () => {
    if (!selA || !selB) return;
    const [tA, dA] = selA.split("|");
    const [tB, dB] = selB.split("|");
    try {
      const result = await getDiff(tA, dA, tB, dB);
      setDiffResult(result);
    } catch (e: any) {
      pushToast("err", `对比失败: ${e.status ?? e}`);
    }
  };

  return (
    <div className="col">
      <h2>历史分析</h2>
      {cum && (
        <StatCard
          title="累计统计（所有分析）"
          metrics={[
            { label: "输入 tokens", value: fmtInt(cum.input_tokens) },
            { label: "输出 tokens", value: fmtInt(cum.output_tokens) },
            { label: "总 tokens", value: fmtInt(cum.total_tokens) },
            { label: "估算成本 (USD)", value: fmtCost(cum.cost_usd) },
            { label: "工具调用次数", value: fmtInt(cum.tool_calls) },
          ]}
          footer={
            <span>
              📦 来源：{fmtInt(cum.runs)} 次分析累计 · 数据存于{" "}
              <code>cumulative_stats.json</code>
            </span>
          }
        />
      )}
      <div className="row">
        <input placeholder="按 ticker 过滤" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button className="btn" onClick={() => load(filter || undefined)}>查询</button>
        <button className="btn-ghost" onClick={reindex}>重建索引</button>
      </div>
      {loading && <p className="muted">加载中…</p>}
      {!loading && errored && (
        <p className="error-text">
          加载失败，请重试。{" "}
          <button className="btn" onClick={() => load(filter || undefined)}>重试</button>
        </p>
      )}
      {!loading && !errored && items.length === 0 && (
        <p className="muted">暂无历史分析记录。</p>
      )}
      <table>
        <thead><tr><th>Ticker</th><th>日期</th><th>评级</th><th>模型</th><th>时间</th></tr></thead>
        <tbody>
          {items.map((it) => (
            <tr key={`${it.ticker}/${it.trade_date}`}>
              <td>
                <button className="btn-ghost" onClick={() => open(it)}>{it.ticker} {it.trade_date}</button>
              </td>
              <td>{it.trade_date}</td>
              <td>{it.rating ?? "—"}</td>
              <td>{it.model ?? "—"}</td>
              <td>{it.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && (
        <div className="card col">
          <h3>{selected.ticker} · {selected.trade_date}</h3>
          <div style={{ color: "var(--c-text-dim)" }}>{selected.summary}</div>
          <textarea placeholder="备注" value={note} onChange={(e) => setNote(e.target.value)} />
          <input placeholder="评分 (good/bad/…)" value={rating} onChange={(e) => setRating(e.target.value)} />
          <div className="row">
            <button className="btn" onClick={save}>保存备注</button>
            <a className="btn-ghost" href={pdfUrl(selected.ticker, selected.trade_date)}
               target="_blank" rel="noreferrer"
               style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)" }}>下载 PDF</a>
          </div>
        </div>
      )}
      <div className="card col">
        <div className="row">
          <label htmlFor="diff-select-a">对比 A</label>
          <select
            id="diff-select-a"
            aria-label="对比 A"
            value={selA}
            onChange={(e) => setSelA(e.target.value)}
          >
            <option value="">-- 选择 A --</option>
            {items.map((it) => (
              <option key={`${it.ticker}|${it.trade_date}`} value={`${it.ticker}|${it.trade_date}`}>
                {it.ticker} {it.trade_date}
              </option>
            ))}
          </select>
          <label htmlFor="diff-select-b">对比 B</label>
          <select
            id="diff-select-b"
            aria-label="对比 B"
            value={selB}
            onChange={(e) => setSelB(e.target.value)}
          >
            <option value="">-- 选择 B --</option>
            {items.map((it) => (
              <option key={`${it.ticker}|${it.trade_date}`} value={`${it.ticker}|${it.trade_date}`}>
                {it.ticker} {it.trade_date}
              </option>
            ))}
          </select>
          <button className="btn" onClick={compare}>对比</button>
        </div>
      </div>
      {diffResult && (
        <div className="card col">
          <div className="row">
            <span>{diffResult.a.ticker} {diffResult.a.trade_date} vs {diffResult.b.ticker} {diffResult.b.trade_date}</span>
            <button className="btn-ghost" onClick={() => setDiffResult(null)}>清除对比</button>
          </div>
          {Object.entries(diffResult.sections).map(([key, sec]) => (
            <div key={key} className="card col">
              <div className="row">
                <span>{key}</span>
                <span className="tag">{sec.changed ? "变更" : "无变更"}</span>
              </div>
              {sec.changed && (
                <pre style={{
                  fontFamily: "monospace",
                  whiteSpace: "pre-wrap",
                  maxHeight: "20rem",
                  overflow: "auto",
                  fontSize: "var(--fz-sm)",
                }}>
                  {sec.diff}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
