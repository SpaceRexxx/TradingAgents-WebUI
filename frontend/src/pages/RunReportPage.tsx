import { Link, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { getRunReport, pdfUrl } from "../api/client";
import Markdown from "../components/Markdown";

type ReportSource =
  | { key: string; title: string }
  | { parent: string; key: string; title: string };

type ReportGroup = {
  title: string;
  sections: ReportSource[];
};

type ReportSection = {
  key: string;
  title: string;
  content: string;
};

type RenderedReportGroup = {
  title: string;
  sections: ReportSection[];
};

const REPORT_GROUPS: ReportGroup[] = [
  {
    title: "第一阶段：分析师团队报告",
    sections: [
      { key: "market_report", title: "市场分析报告" },
      { key: "sentiment_report", title: "舆情分析报告" },
      { key: "news_report", title: "新闻分析报告" },
      { key: "fundamentals_report", title: "基本面分析报告" },
    ],
  },
  {
    title: "第二阶段：研究团队辩论",
    sections: [
      { parent: "investment_debate_state", key: "bull_history", title: "多头研究员辩论" },
      { parent: "investment_debate_state", key: "bear_history", title: "空头研究员辩论" },
      { key: "investment_plan", title: "研究经理总结" },
    ],
  },
  {
    title: "第三阶段：交易团队计划",
    sections: [
      { key: "trader_investment_plan", title: "交易员计划" },
    ],
  },
  {
    title: "第四/五阶段：风险管理与最终决策",
    sections: [
      { parent: "risk_debate_state", key: "aggressive_history", title: "激进型分析师辩论" },
      { parent: "risk_debate_state", key: "conservative_history", title: "保守型分析师辩论" },
      { parent: "risk_debate_state", key: "neutral_history", title: "中立型分析师辩论" },
      { key: "final_trade_decision", title: "最终投资决策" },
    ],
  },
];

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function getContent(finalState: Record<string, unknown>, source: ReportSource): string {
  if ("parent" in source) return str(record(finalState[source.parent])[source.key]);
  return str(finalState[source.key]);
}

function buildGroups(finalState: Record<string, unknown>): RenderedReportGroup[] {
  return REPORT_GROUPS.map((group) => ({
    ...group,
    sections: group.sections.flatMap((source) => {
      const content = getContent(finalState, source);
      if (!content) return [];
      const key = "parent" in source ? `${source.parent}.${source.key}` : source.key;
      return [{ key, title: source.title, content }];
    }),
  })).filter((group) => group.sections.length > 0);
}

export default function RunReportPage() {
  const { ticker = "", tradeDate = "" } = useParams();
  const [finalState, setFinalState] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    getRunReport(ticker, tradeDate)
      .then((data) => {
        if (alive) setFinalState(data.final_state);
      })
      .catch((e: any) => {
        if (alive) setError(`加载报告失败: ${e.status ?? e}`);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [ticker, tradeDate]);

  const groups = useMemo(
    () => buildGroups(finalState ?? {}),
    [finalState],
  );

  return (
    <div className="col">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{ticker} 完整分析报告</h2>
          <div className="muted">分析日期：{tradeDate}</div>
        </div>
        <div className="row">
          <Link className="btn-ghost" to="/history" style={{ textDecoration: "none" }}>
            返回历史
          </Link>
          <a
            className="btn"
            href={pdfUrl(ticker, tradeDate)}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "none", padding: "var(--sp-2) var(--sp-4)" }}
          >
            下载 PDF
          </a>
        </div>
      </div>

      {loading && <p className="muted">加载报告中…</p>}
      {!loading && error && <p className="error-text">{error}</p>}
      {!loading && !error && groups.length === 0 && (
        <p className="muted">该分析记录没有可显示的报告内容。</p>
      )}
      {!loading && !error && groups.map((group) => (
        <section key={group.title} className="card col">
          <h3>{group.title}</h3>
          {group.sections.map((sec) => (
            <article key={sec.key}>
              <h4>{sec.title}</h4>
              <Markdown>{sec.content}</Markdown>
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}
