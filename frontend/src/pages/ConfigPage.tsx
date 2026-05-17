import { useEffect, useState } from "react";
import {
  listProviders, setProviderKey, testProvider, getSettings, updateSettings,
} from "../api/client";
import type { ProviderInfo, TestProviderResponse, AppSettings } from "../api/types";
import { useAppStore } from "../store/appStore";

const LLM_FIELDS: { key: keyof AppSettings; label: string; ph: string }[] = [
  { key: "llm_provider", label: "供应商", ph: "DeepSeek" },
  { key: "deep_think_llm", label: "深度引擎模型", ph: "deepseek-chat" },
  { key: "quick_think_llm", label: "快速引擎模型", ph: "deepseek-reasoner" },
  { key: "backend_url", label: "Base URL", ph: "https://api.deepseek.com/v1" },
];

export default function ConfigPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, TestProviderResponse>>({});
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState(false);
  const [resultsDir, setResultsDir] = useState("");
  const [llm, setLlm] = useState<Record<string, string>>({});
  const pushToast = useAppStore((s) => s.pushToast);

  const load = () => {
    setErrored(false);
    return listProviders()
      .then((r) => { setProviders(r.providers); })
      .catch((e) => { setErrored(true); pushToast("err", `加载 providers 失败: ${e.status ?? e}`); })
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setResultsDir(s.results_dir ?? "");
        setLlm({
          llm_provider: s.llm_provider ?? "",
          deep_think_llm: s.deep_think_llm ?? "",
          quick_think_llm: s.quick_think_llm ?? "",
          backend_url: s.backend_url ?? "",
        });
      })
      .catch(() => {});
  }, []);

  const saveResultsDir = async () => {
    try {
      const s = await updateSettings({ results_dir: resultsDir });
      setResultsDir(s.results_dir);
      pushToast("ok", "下载目录已保存（新分析生效）");
    } catch (e: any) {
      pushToast("err", `保存失败 (${e.status ?? e})`);
    }
  };

  const saveLlm = async () => {
    try {
      const patch: Partial<AppSettings> = {};
      for (const { key } of LLM_FIELDS) {
        const v = (llm[key] ?? "").trim();
        if (v) patch[key] = v;
      }
      const s = await updateSettings(patch);
      setLlm({
        llm_provider: s.llm_provider,
        deep_think_llm: s.deep_think_llm,
        quick_think_llm: s.quick_think_llm,
        backend_url: s.backend_url,
      });
      pushToast("ok", "模型 / 供应商已保存（新分析生效）");
    } catch (e: any) {
      pushToast("err", `保存失败 (${e.status ?? e})`);
    }
  };

  const saveKey = async (id: string) => {
    try {
      await setProviderKey(id, keys[id] ?? "");
      pushToast("ok", `${id} key 已保存`);
      setKeys((k) => ({ ...k, [id]: "" }));
      load();
    } catch (e: any) {
      pushToast("err", `保存失败 (${e.status ?? e})`);
    }
  };

  const runTest = async (id: string) => {
    try {
      const r = await testProvider(id);
      setResults((m) => ({ ...m, [id]: r }));
    } catch (e: any) {
      pushToast("err", `测试失败 (${e.status ?? e})`);
    }
  };

  return (
    <div className="col">
      <h2>下载目录</h2>
      <p style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
        分析结果（JSON / PDF / SQLite 索引 / 累计统计）的存放目录。修改后对新分析生效。
      </p>
      <div className="row">
        <input
          aria-label="下载目录"
          style={{ flex: 1, minWidth: 280 }}
          placeholder="/path/to/results"
          value={resultsDir}
          onChange={(e) => setResultsDir(e.target.value)}
        />
        <button className="btn" disabled={!resultsDir.trim()} onClick={saveResultsDir}>
          保存
        </button>
      </div>

      <h2>模型 / 供应商</h2>
      <p style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
        分析所用的供应商与模型（写入 .env + 进程环境，对新分析生效；右上角徽标显示当前深度模型）。留空的字段不修改。
      </p>
      <div className="col" style={{ gap: "var(--sp-2)", maxWidth: 520 }}>
        {LLM_FIELDS.map((f) => (
          <label key={f.key} className="row" style={{ gap: "var(--sp-3)", alignItems: "center" }}>
            <span style={{ width: 110, color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
              {f.label}
            </span>
            <input
              aria-label={f.label}
              style={{ flex: 1, minWidth: 240 }}
              placeholder={f.ph}
              value={llm[f.key] ?? ""}
              onChange={(e) => setLlm((m) => ({ ...m, [f.key]: e.target.value }))}
            />
          </label>
        ))}
        <button className="btn" style={{ width: "fit-content" }} onClick={saveLlm}>
          保存模型设置
        </button>
      </div>

      <h2>Provider 配置</h2>
      <p style={{ color: "var(--c-text-dim)", fontSize: "var(--fz-sm)" }}>
        API key 只写不回显。提交后写入 .env + 进程环境。
      </p>
      {loading && <p className="muted">加载中…</p>}
      {!loading && errored && providers.length === 0 && (
        <p className="error-text">
          加载失败，请重试。{" "}
          <button className="btn" onClick={() => load()}>重试</button>
        </p>
      )}
      <table>
        <thead><tr><th>Provider</th><th>已配置</th><th>设置 Key</th><th>测试</th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id}>
              <td>{p.name}<div style={{ color: "var(--c-text-dim)", fontSize: 12 }}>{p.base_url ?? "—"}</div></td>
              <td><span className={`dot ${p.configured ? "dot-ok" : "dot-err"}`} /> {p.configured ? "是" : "否"}</td>
              <td>
                <div className="row">
                  <input type="password" placeholder="API Key" data-testid={`key-input-${p.id}`}
                    value={keys[p.id] ?? ""}
                    onChange={(e) => setKeys((k) => ({ ...k, [p.id]: e.target.value }))} />
                  <button className="btn" data-testid={`key-save-${p.id}`} onClick={() => saveKey(p.id)}>保存</button>
                </div>
              </td>
              <td>
                <button className="btn-ghost" data-testid={`key-test-${p.id}`} onClick={() => runTest(p.id)}>测试</button>
                {results[p.id] && (
                  <div style={{ fontSize: 12, color: results[p.id].ok ? "var(--c-ok)" : "var(--c-err)" }}>
                    {results[p.id].reason}{results[p.id].status ? ` (${results[p.id].status})` : ""}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
