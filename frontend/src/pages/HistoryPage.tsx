import { Fragment, useEffect, useState, useCallback } from "react";
import {
  listHistory, patchHistory, pdfUrl, reportUrl, getDiff, getCumulativeStats, reindexHistory,
} from "../api/client";
import type { HistoryItem, DiffResponse, CumulativeStats } from "../api/types";
import StatCard, { fmtInt, fmtCost } from "../components/StatCard";
import { useAppStore } from "../store/appStore";
import Markdown from "../components/Markdown";

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
  const selectedKey = selected ? `${selected.ticker}/${selected.trade_date}` : null;

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
      {!loading && !errored && items.length > 0 && (
        <div className="history-grid">
          {items.map((it) => (
            <Fragment key={`${it.ticker}/${it.trade_date}`}>
              <article className="history-card">
                <a className="history-card-code" href={reportUrl(it.ticker, it.trade_date)}>
                  {it.ticker}
                </a>
                <div className="history-card-row">
                  <span>日期</span>
                  <strong>{it.trade_date}</strong>
                </div>
                <div className="history-card-row">
                  <span>评级</span>
                  <strong>{it.rating ?? "—"}</strong>
                </div>
                <div className="history-card-row">
                  <span>模型</span>
                  <strong>{it.model ?? "—"}</strong>
                </div>
                <button
                  className="btn-ghost history-card-action"
                  aria-expanded={selectedKey === `${it.ticker}/${it.trade_date}`}
                  onClick={() => open(it)}
                >
                  备注
                </button>
              </article>
              {selectedKey === `${it.ticker}/${it.trade_date}` && (
                <div className="card col history-editor">
                  <h3>{selected?.ticker} · {selected?.trade_date}</h3>
                  <div style={{ color: "var(--c-text-dim)" }}>{selected?.summary}</div>
                  <textarea placeholder="备注" value={note} onChange={(e) => setNote(e.target.value)} />
                  <input placeholder="评分 (good/bad/…)" value={rating} onChange={(e) => setRating(e.target.value)} />
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    <button className="btn" onClick={save}>保存备注</button>
                    <button className="btn-ghost" onClick={() => setSelected(null)}>取消</button>
                    <a className="btn-ghost" href={pdfUrl(it.ticker, it.trade_date)}
                       target="_blank" rel="noreferrer"
                       style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)" }}>下载 PDF</a>
                  </div>
                </div>
              )}
            </Fragment>
          ))}
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
            <section key={key} className="card col">
              <div className="row">
                <span>{sec.title || key}</span>
                <span className="tag">{sec.changed ? "变更" : "无变更"}</span>
              </div>
              <div className="diff-panels">
                <article className="diff-panel">
                  <h4>{diffResult.a.ticker} {diffResult.a.trade_date}</h4>
                  {sec.a_text ? <Markdown>{sec.a_text}</Markdown> : <p className="muted">无内容</p>}
                </article>
                <article className="diff-panel">
                  <h4>{diffResult.b.ticker} {diffResult.b.trade_date}</h4>
                  {sec.b_text ? <Markdown>{sec.b_text}</Markdown> : <p className="muted">无内容</p>}
                </article>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
