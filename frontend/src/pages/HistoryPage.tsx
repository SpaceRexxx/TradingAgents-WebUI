import { useEffect, useState, useCallback } from "react";
import { listHistory, patchHistory, pdfUrl } from "../api/client";
import type { HistoryItem } from "../api/types";
import { useAppStore } from "../store/appStore";

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState("");
  const pushToast = useAppStore((s) => s.pushToast);

  const load = useCallback((ticker?: string) => {
    listHistory(ticker || undefined)
      .then((r) => setItems(r.items))
      .catch((e) => pushToast("err", `加载历史失败: ${e.status ?? e}`));
  }, [pushToast]);

  useEffect(() => { load(); }, [load]);

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

  return (
    <div className="col">
      <h2>历史分析</h2>
      <div className="row">
        <input placeholder="按 ticker 过滤" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button className="btn" onClick={() => load(filter || undefined)}>查询</button>
      </div>
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
    </div>
  );
}
