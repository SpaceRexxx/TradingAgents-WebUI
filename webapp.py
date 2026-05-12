# webapp.py (v2 - 包含持久化历史记录功能)
# 功能:
# - 【新】分析完成后自动保存结果 (JSON + PDF) 到 results/ 目录
# - 【新】侧边栏增加 "历史分析记录" 浏览器
# - 【新】支持点击加载历史记录，并立即下载对应的 PDF
# - 使用 Playwright 生成高质量 PDF 报告
# - 实时更新代理状态和进度

import streamlit as st
import streamlit.components.v1 as _st_components
import datetime
from pathlib import Path
import re
import io
import asyncio
import os
import json
import subprocess
import platform

# 自动加载 .env 文件（兼容未激活 conda 环境的情况）
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except ImportError:
    pass

# 【新增】更新 .env 文件的辅助函数
def update_dotenv_file(key_name, value):
    """持久化保存 API Key 到本地 .env 文件"""
    env_path = Path(__file__).parent / ".env"
    lines = []
    found = False
    
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    new_line = f"{key_name}={value}\n"
    
    # 查找并替换现有的 Key
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key_name}="):
            lines[i] = new_line
            found = True
            break
            
    if not found:
        # 如果没找到且 .env 不为空且最后一行没换行，补一个换行
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_line)
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True

# 导入PDF生成库 (同步版)
import markdown2
from playwright.sync_api import sync_playwright

# 导入项目核心组件
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType
from tradingagents.storage import sqlite_history

# --- 页面基础配置 ---
st.set_page_config(layout="wide", page_title="TradingAgents Web")

# Fix browser autocomplete warnings: Streamlit renders inputs with autocomplete=""
# (empty string), which browsers flag as invalid. Inject via components iframe so
# the script can walk up to window.parent and patch all inputs in the main document.
_st_components.html("""
<script>
(function() {
    function patch(doc) {
        doc.querySelectorAll('input').forEach(function(el) {
            var ac = el.getAttribute('autocomplete');
            if (ac === null || ac === '') {
                el.setAttribute('autocomplete', el.type === 'password' ? 'off' : 'off');
            }
        });
    }
    function run() {
        try { patch(window.parent.document); } catch(e) {}
        try { patch(document); } catch(e) {}
    }
    var observer = new MutationObserver(run);
    try {
        observer.observe(window.parent.document.body, { childList: true, subtree: true });
    } catch(e) {}
    run();
})();
</script>
""", height=0)

# --- Stage 9: 数据源降级检测（启动时一次性 quick health） ---
def _detect_degraded_sources() -> list[str]:
    """轻量检测：哪些数据源不可用，返回降级原因列表。"""
    degraded = []
    import shutil as _shutil
    if not _shutil.which("opencli"):
        degraded.append("OpenCLI 未安装 → 雪球 / Reddit / 新浪 数据源不可用")
    try:
        import akshare  # noqa
    except ImportError:
        degraded.append("akshare 未安装 → A 股数据源不可用（千股千评 / 公告 / 财联社）")
    return degraded


# --- 全局 CSS 视觉系统（Stage 4）---
st.markdown(
    """
    <style>
    /* 顶部 tabs：更突出 */
    div[data-testid="stTabs"] button[role="tab"] {
        font-size: 16px !important;
        font-weight: 600 !important;
        padding-top: 12px !important;
        padding-bottom: 12px !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background-color: rgba(34, 197, 94, 0.08) !important;
        border-bottom: 3px solid #22c55e !important;
        color: #22c55e !important;
    }

    /* Container 边框：更柔和的圆角 + 微微阴影 */
    div[data-testid="stContainer"][class*="border"] {
        border-radius: 10px !important;
    }

    /* st.info / warning / error 卡片：左侧色条更明显 */
    div[data-testid="stAlert"] {
        border-left-width: 4px !important;
        border-radius: 8px !important;
    }

    /* 主标题更紧凑（默认间距太大）*/
    h1 {
        padding-top: 0 !important;
        margin-bottom: 0.5rem !important;
    }

    /* 让 sidebar 略窄一些，给主区域留更多空间 */
    section[data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 320px !important;
    }

    /* expander 标题更醒目 */
    summary {
        font-weight: 600 !important;
    }

    /* button：默认主操作按钮高亮成品牌绿 */
    button[kind="primary"], button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%) !important;
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #16a34a 0%, #15803d 100%) !important;
    }

    /* 表格：紧凑 + 边框柔和 */
    table {
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 主标题 + 副标题
_t_col1, _t_col2 = st.columns([5, 2])
with _t_col1:
    st.title("📈 TradingAgents")
    st.caption("多代理智能交易分析框架 · v2 · A 股 / 美股 / 港股")
with _t_col2:
    st.write("")
    st.write("")
    # 简短状态指示器（实时显示当前 provider + model）
    try:
        _hdr_provider = st.session_state.ui_prefs.get("provider", "DeepSeek")
        _hdr_deep = st.session_state.ui_prefs.get(f"{_hdr_provider.lower()}_deep") or "未选"
        st.caption(f"🔌 {_hdr_provider}  ·  🧠 {_hdr_deep}")
    except Exception:
        pass

# Stage 9: 启动时检测降级数据源并在顶部展示 banner
_degraded = _detect_degraded_sources()
if _degraded:
    with st.container(border=True):
        st.warning(
            "⚠️ **部分数据源降级运行中**　·　不影响主流程，但相关报告会简化。"
        )
        for _reason in _degraded:
            st.caption(f"• {_reason}")
        st.caption("👉 详细诊断和修复建议见 **🏥 诊断** tab")

# --- 定义团队结构 ---
TEAMS_STRUCTURE = {
    "分析师团队": ["市场分析师", "舆情分析师", "新闻分析师", "基本面分析师"],
    "研究团队": ["多头研究员", "空头研究员", "研究经理"],
    "交易团队": ["交易员"],
    "风险管理团队": ["激进型分析师", "保守型分析师", "中立型分析师", "投资组合经理"],
}
SENDER_MAP = {
    "Market Analyst": "市场分析师", "News Analyst": "新闻分析师",
    "Social Analyst": "舆情分析师", "Fundamentals Analyst": "基本面分析师",
    "Bull Researcher": "多头研究员", "Bear Researcher": "空头研究员",
    "Research Manager": "研究经理", "Trader": "交易员",
    "Risky Analyst": "激进型分析师", "Safe Analyst": "保守型分析师",
    "Neutral Analyst": "中立型分析师", "Risk Judge": "投资组合经理"
}
# 【修改】初始化 Session State 及其依赖项 (提前到此处)
if 'ui_prefs' not in st.session_state:
    PREFS_FILE = ".ui_prefs.json"
    def _load_prefs():
        if os.path.exists(PREFS_FILE):
            try:
                with open(PREFS_FILE, "r") as f: return json.load(f)
            except: pass
        return {}
    st.session_state.ui_prefs = _load_prefs()

# 【修改】动态获取结果保存目录
RESULTS_DIR = Path(st.session_state.ui_prefs.get("results_dir", str(DEFAULT_CONFIG.get("results_dir", "./results"))))
if not RESULTS_DIR.exists():
    try: RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    except: pass

# --- 初始化 Session State ---
if 'agent_status' not in st.session_state: st.session_state.agent_status = {}
if 'agent_reports' not in st.session_state: st.session_state.agent_reports = {}
# Stage 6: token / 工具调用统计
if 'token_stats' not in st.session_state:
    st.session_state.token_stats = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
        "tool_calls": {},  # name -> count
    }
if 'messages' not in st.session_state: st.session_state.messages = []
if 'final_state' not in st.session_state: st.session_state.final_state = None
if 'previous_sender' not in st.session_state: st.session_state.previous_sender = None
if 'show_live_report_view' not in st.session_state: st.session_state.show_live_report_view = False
if 'start_analysis' not in st.session_state: st.session_state.start_analysis = False # 【修改】确保存在

# 从 chunk 中提取每个 agent 的输出报告，用于"点击展开查看"
AGENT_REPORT_EXTRACTORS = {
    "市场分析师":       lambda c: c.get("market_report"),
    "舆情分析师":       lambda c: c.get("sentiment_report"),
    "新闻分析师":       lambda c: c.get("news_report"),
    "基本面分析师":     lambda c: c.get("fundamentals_report"),
    "多头研究员":       lambda c: (c.get("investment_debate_state") or {}).get("bull_history"),
    "空头研究员":       lambda c: (c.get("investment_debate_state") or {}).get("bear_history"),
    "研究经理":         lambda c: c.get("investment_plan"),
    "交易员":           lambda c: c.get("trader_investment_plan"),
    "激进型分析师":     lambda c: (c.get("risk_debate_state") or {}).get("aggressive_history"),
    "保守型分析师":     lambda c: (c.get("risk_debate_state") or {}).get("conservative_history"),
    "中立型分析师":     lambda c: (c.get("risk_debate_state") or {}).get("neutral_history"),
    "投资组合经理":     lambda c: c.get("final_trade_decision"),
}
if 'current_analysis_paths' not in st.session_state: st.session_state.current_analysis_paths = None # 【新增】
if 'pdf_data' not in st.session_state: st.session_state.pdf_data = None # 【新增】缓存 PDF 字节流


# --- UI 首选项持久化 helper（模块级，供 sidebar/tabs 共享）---
PREFS_FILE = ".ui_prefs.json"


def save_prefs(prefs: dict) -> None:
    """把当前 UI 首选项写盘，下次启动自动加载。"""
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f)


def update_pref(key: str, value) -> None:
    """更新单个首选项并持久化。"""
    st.session_state.ui_prefs[key] = value
    save_prefs(st.session_state.ui_prefs)


# --- Stage 7: 分析模板（一键应用预置参数组合）---
ANALYSIS_TEMPLATES = {
    "🎯 标准（默认）": {
        "depth": 2,
        "lookback_days": 30,
        "news_lookback_days": 7,
        "analysts": ["市场分析师", "舆情分析师", "新闻分析师", "基本面分析师"],
        "description": "中等深度，覆盖全部 4 个分析师，适合日常分析",
    },
    "⚡ 快速扫描": {
        "depth": 0,
        "lookback_days": 14,
        "news_lookback_days": 3,
        "analysts": ["市场分析师", "新闻分析师"],
        "description": "极浅深度，只跑 2 个分析师，快速给出方向判断",
    },
    "🔬 深度调研": {
        "depth": 3,
        "lookback_days": 90,
        "news_lookback_days": 14,
        "analysts": ["市场分析师", "舆情分析师", "新闻分析师", "基本面分析师"],
        "description": "3 轮深度辩论，长期视角，适合重要决策",
    },
    "📰 事件驱动": {
        "depth": 1,
        "lookback_days": 7,
        "news_lookback_days": 3,
        "analysts": ["新闻分析师", "舆情分析师"],
        "description": "短窗口，专注新闻和舆情，适合突发事件分析",
    },
    "💎 价值投资": {
        "depth": 2,
        "lookback_days": 120,
        "news_lookback_days": 14,
        "analysts": ["基本面分析师", "市场分析师", "新闻分析师"],
        "description": "长窗口 + 重基本面，适合中长线持有的判断",
    },
}


# --- 各 LLM 提供商的元数据（模块级，供 sidebar/tabs 共享）---
PROVIDER_OPTIONS = {
    "DeepSeek": "https://api.deepseek.com/v1",
    "NVIDIA": "https://integrate.api.nvidia.com/v1",
    "火山引擎 (Volcengine)": "https://ark.cn-beijing.volces.com/api/v3",
    "OpenAI": "https://api.openai.com/v1",
    "Google": "https://generativelen/v1",
}
PROVIDER_ENV_KEY_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "火山引擎 (volcengine)": "ARK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}
SHALLOW_AGENT_OPTIONS = {
    "deepseek": [
        ("DeepSeek V4 Flash - 最新快速模型", "deepseek-v4-flash"),
        ("DeepSeek V3.2 通用", "deepseek-chat"),
        ("DeepSeek V3.2 深度思考", "deepseek-reasoner"),
    ],
    "nvidia": [("NVIDIA-DeepSeek-V3", "deepseek-ai/deepseek-v3.2")],
    "火山引擎 (volcengine)": [("Seed-2.0", "ep-20260315170816-rdcb9")],
    "openai": [("GPT-4o mini - 快速高效", "gpt-4o-mini"), ("GPT-4o - 标准模型", "gpt-4o")],
    "google": [("Gemini 1.5 Flash - 高性价比", "gemini-1.5-flash-latest")],
}
DEEP_AGENT_OPTIONS = {
    "deepseek": [
        ("DeepSeek V4 Pro - 最新旗舰模型", "deepseek-v4-pro"),
        ("DeepSeek V4 Flash - 最新快速模型", "deepseek-v4-flash"),
        ("DeepSeek V3.2 通用", "deepseek-chat"),
        ("DeepSeek V3.2 深度思考", "deepseek-reasoner"),
    ],
    "nvidia": [("NVIDIA-DeepSeek-V3 (Thinking)", "deepseek-ai/deepseek-v3.2")],
    "火山引擎 (volcengine)": [("Seed-2.0 (Thinking)", "ep-20260315170816-rdcb9")],
    "openai": [("GPT-4o - 旗舰模型", "gpt-4o"), ("GPT-4 Turbo - 高性能", "gpt-4-turbo")],
    "google": [("Gemini 1.5 Pro - 先进推理", "gemini-1.5-pro-latest")],
}


def _get_opt_idx(opts: list, saved_val: str) -> int:
    """在 (label, model_id) 列表里找到 saved_val 对应的索引；找不到返回 0。"""
    for i, opt in enumerate(opts):
        if opt[1] == saved_val:
            return i
    return 0


# --- UI helper：行动化错误与进度展示（Stage 2）---
def show_error_with_fix(
    title: str,
    detail: str = "",
    fix_steps: list[str] | None = None,
    level: str = "error",
):
    """统一的"错误 + 修复建议"展示组件。

    title: 简短错误标题（必填，例如 '缺少 API Key'）
    detail: 详细描述（可选，例如 'DeepSeek 调用返回 401'）
    fix_steps: 可执行的修复步骤列表（每条一句）
    level: 'error' | 'warning' | 'info'
    """
    icon = "❌" if level == "error" else ("⚠️" if level == "warning" else "💡")
    func = {"error": st.error, "warning": st.warning, "info": st.info}[level]
    func(f"{icon} **{title}**" + (f"\n\n{detail}" if detail else ""))
    if fix_steps:
        with st.expander("📌 修复建议（点击展开）", expanded=True):
            for i, step in enumerate(fix_steps, 1):
                st.markdown(f"**{i}.** {step}")


# 五阶段定义（用于进度 stepper）
ANALYSIS_PHASES = [
    {"key": "analysts", "label": "分析师团队", "icon": "📊"},
    {"key": "research", "label": "研究团队辩论", "icon": "🥊"},
    {"key": "trader",   "label": "交易团队",   "icon": "💼"},
    {"key": "risk",     "label": "风险管理辩论", "icon": "⚖️"},
    {"key": "decision", "label": "最终决策",   "icon": "🎯"},
]


def detect_current_phase(chunk: dict) -> tuple[str, int]:
    """从 streaming chunk 推断当前所处阶段。返回 (phase_key, progress_0_100)。"""
    if chunk.get("final_trade_decision"):
        return "decision", 100
    if chunk.get("risk_debate_state") and chunk["risk_debate_state"].get("history"):
        return "risk", 85
    if chunk.get("trader_investment_plan"):
        return "trader", 70
    if chunk.get("investment_plan"):
        return "research", 55
    if chunk.get("investment_debate_state") and chunk["investment_debate_state"].get("history"):
        return "research", 35
    if any(chunk.get(f"{k}_report") for k in ("market", "news", "sentiment", "fundamentals")):
        return "analysts", 15
    return "analysts", 5


def render_phase_stepper(current_phase_key: str, elapsed_seconds: float | None = None):
    """渲染 5 阶段水平进度卡片。"""
    # 确定每个阶段的状态：done / active / pending
    phase_keys = [p["key"] for p in ANALYSIS_PHASES]
    try:
        current_idx = phase_keys.index(current_phase_key)
    except ValueError:
        current_idx = 0

    cols = st.columns(len(ANALYSIS_PHASES))
    for i, (col, phase) in enumerate(zip(cols, ANALYSIS_PHASES)):
        with col:
            if i < current_idx:
                state_icon = "✅"
                bg = "#1e3a2f"   # 深绿
                label_color = "#9be9a8"
            elif i == current_idx:
                state_icon = "⏳"
                bg = "#3a3520"   # 深黄
                label_color = "#f7ce46"
            else:
                state_icon = "⚪"
                bg = "#1f2937"   # 深灰
                label_color = "#94a3b8"
            st.markdown(
                f"""<div style="background:{bg};border-radius:8px;padding:10px;text-align:center;">
                <div style="font-size:22px;line-height:1.2;">{phase['icon']}</div>
                <div style="color:{label_color};font-size:12px;font-weight:600;margin-top:4px;">{phase['label']}</div>
                <div style="color:{label_color};font-size:14px;margin-top:2px;">{state_icon}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # 已耗时显示
    if elapsed_seconds is not None and elapsed_seconds > 0:
        st.caption(f"⏱️ 已耗时：**{format_elapsed(elapsed_seconds)}**" +
                   (f" · 当前阶段：**{ANALYSIS_PHASES[current_idx]['label']}**" if current_idx < len(ANALYSIS_PHASES) else ""))


def format_elapsed(seconds: float) -> str:
    """把秒数格式化为 'M 分 SS 秒'。"""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    return f"{seconds // 60} 分 {seconds % 60:02d} 秒"


# --- Helper 函数 ---
def reset_state():
    """重置整个应用的会话状态，用于开始新的分析"""
    status_dict = {agent: "pending" for team in TEAMS_STRUCTURE.values() for agent in team}
    st.session_state.agent_status = status_dict
    st.session_state.agent_reports = {}
    st.session_state.messages = []
    st.session_state.final_state = None
    st.session_state.previous_sender = None
    st.session_state.show_live_report_view = False
    st.session_state.start_analysis = False # 【新增】
    st.session_state.current_analysis_paths = None # 【新增】
    st.session_state.pdf_data = None # 【新增】
    # Stage 6: 重置 token 统计
    st.session_state.token_stats = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
        "tool_calls": {},
    }


# Stage 6 helper：从 chunk 累计 token / tool 调用
def _accumulate_token_stats(chunk: dict):
    """从 streaming chunk 的消息中提取 token usage，累计到 session_state.token_stats。"""
    msgs = chunk.get("messages") or []
    if not msgs:
        return
    stats = st.session_state.token_stats
    for msg in msgs[-3:]:  # 只看最近的几条，避免重复累加（chunk 是增量）
        usage = getattr(msg, "usage_metadata", None) or getattr(msg, "response_metadata", {})
        if isinstance(usage, dict):
            # langchain 的 usage_metadata 格式
            it = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            ot = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            tt = usage.get("total_tokens") or (it + ot)
            if tt:
                # 因为 chunk 是累加流，简单办法：只取最近这次的最大值；用最近一次覆盖
                stats["input_tokens"] = max(stats["input_tokens"], it)
                stats["output_tokens"] = max(stats["output_tokens"], ot)
                stats["total_tokens"] = max(stats["total_tokens"], tt)
        # 工具调用计数
        tc = getattr(msg, "tool_calls", None)
        if tc:
            for call in tc:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                if name:
                    stats["tool_calls"][name] = stats["tool_calls"].get(name, 0) + 1


def _format_token_stats(stats: dict, model: str = "") -> dict:
    """把 token_stats 转成展示用的字典；包含粗略成本估算。"""
    # DeepSeek V4 估算价格（USD / 1M tokens）—— 用户实际价格请以 DeepSeek 官方为准
    pricing = {
        "deepseek-v4-flash": (0.50, 1.50),
        "deepseek-v4-pro":   (1.00, 3.00),
        "deepseek-chat":     (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
        "gpt-4o":            (5.00, 15.00),
        "gpt-4o-mini":       (0.15, 0.60),
    }
    in_price, out_price = pricing.get(model, (0.0, 0.0))
    input_tokens = stats.get("input_tokens", 0)
    output_tokens = stats.get("output_tokens", 0)
    cost_usd = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return {
        "输入 tokens": f"{input_tokens:,}",
        "输出 tokens": f"{output_tokens:,}",
        "总 tokens":   f"{stats.get('total_tokens', input_tokens + output_tokens):,}",
        "估算成本":     f"${cost_usd:.4f}" if cost_usd > 0 else "—",
        "工具调用":     sum(stats.get("tool_calls", {}).values()),
    }

# 【新增】加载历史记录的函数（Stage 3：cache_data 加速）
@st.cache_data(ttl=120, show_spinner=False)
def load_historical_analyses_cached(base_dir_str: str):
    """带缓存的历史目录扫描；2 分钟内重复调用直接复用结果。

    ``base_dir_str`` 必须是字符串（cache_data 要求参数 hashable），
    新分析完成后会用 ``st.cache_data.clear()`` 显式失效。
    """
    return load_historical_analyses(Path(base_dir_str))


def load_historical_analyses(base_dir):
    """扫描结果目录并返回一个按 Ticker 分组的字典（无缓存版本，cached 包一层）"""
    history = {}
    json_files = list(base_dir.rglob("final_state_report.json"))
    for json_path in json_files:
        try:
            date = json_path.parent.name
            ticker = json_path.parent.parent.name
            pdf_path = json_path.parent / "report.pdf"
            
            if ticker not in history:
                history[ticker] = []
            
            if pdf_path.exists():
                history[ticker].append({
                    "date": date,
                    "json_path": str(json_path),
                    "pdf_path": str(pdf_path)
                })
        except Exception as e:
            print(f"Error loading history from {json_path}: {e}")
            
    # 按日期对每个 ticker 的记录进行排序
    for ticker in history:
        history[ticker].sort(key=lambda x: x['date'], reverse=True)
        
    return history

# 【新增】点击加载按钮时的回调函数
def load_selected_analysis(json_path):
    """加载选定的历史 JSON 文件到 session_state"""
    reset_state() # 首先清空当前状态
    # 用户切换历史记录 → 顺便清掉历史扫描缓存，确保下次 tab_history 看最新
    try:
        load_historical_analyses_cached.clear()
    except Exception:
        pass
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        st.session_state.final_state = data
        st.session_state.current_analysis_paths = {
            'json': json_path,
            'pdf': str(Path(json_path).parent / "report.pdf")
        }
        st.session_state.show_live_report_view = False
    except Exception as e:
        st.error(f"加载历史记录失败: {e}")

# 【新增】序列化和保存结果的函数
def save_analysis_results(final_state, ticker, analysis_date, config, pdf_data):
    """将 final_state 和 PDF 保存到磁盘"""
    try:
        save_path = Path(config["results_dir"]) / ticker / analysis_date
        save_path.mkdir(parents=True, exist_ok=True)
        
        # 1. 保存 PDF
        pdf_file_path = save_path / "report.pdf"
        with open(pdf_file_path, "wb") as f:
            f.write(pdf_data)
            
        # 2. 序列化并保存 state (排除不可序列化的 'messages')
        serializable_state = {k: v for k, v in final_state.items() if k != 'messages'}
        json_file_path = save_path / "final_state_report.json"
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(serializable_state, f, ensure_ascii=False, indent=4)
            
        # 3. 更新 session state 以引用这些新保存的路径
        st.session_state.current_analysis_paths = {
            'json': str(json_file_path),
            'pdf': str(pdf_file_path)
        }
        # 4. 失效历史扫描缓存，下次进入 📚 历史分析 tab 能看到新记录
        try:
            load_historical_analyses_cached.clear()
        except Exception:
            pass
        # 5. 把新分析索引进 SQLite，启用快速查询和 A/B 对比
        try:
            sqlite_history.index_one_analysis(
                config["results_dir"],
                ticker=ticker,
                trade_date=analysis_date,
                json_path=str(json_file_path),
                pdf_path=str(pdf_file_path),
                decision_text=final_state.get("final_trade_decision", ""),
                model=config.get("deep_think_llm"),
                provider=config.get("llm_provider"),
                has_position=config.get("has_position"),
            )
        except Exception as _exc:
            # 索引失败不影响主流程
            pass
        return True
    except Exception as e:
        st.error(f"保存分析结果时出错: {e}")
        return False

def display_live_report(state_chunk):
    """(用于流式更新)根据给定的状态块(chunk)来渲染实时报告视图"""
    st.subheader("实时报告")
    if "risk_debate_state" in state_chunk and state_chunk["risk_debate_state"]["history"]:
        st.subheader("第四/五阶段：风险管理与最终决策")
        risk_state = state_chunk["risk_debate_state"]
        r_col1, r_col2, r_col3 = st.columns(3)
        with r_col1: st.error("**激进派观点**"); st.markdown(risk_state.get("risky_history", ""))
        with r_col2: st.info("**中立派观点**"); st.markdown(risk_state.get("neutral_history", ""))
        with r_col3: st.warning("**保守派观点**"); st.markdown(risk_state.get("safe_history", ""))
        if risk_state.get("judge_decision"): st.success("**最终决策 (投资组合经理):**"); st.markdown(risk_state["judge_decision"])
    elif "trader_investment_plan" in state_chunk and state_chunk["trader_investment_plan"]:
        st.subheader("第三阶段：交易团队计划"); st.markdown(state_chunk["trader_investment_plan"])
    elif "investment_debate_state" in state_chunk and state_chunk["investment_debate_state"]["history"]:
        st.subheader("第二阶段：研究团队辩论与决策")
        debate_state = state_chunk["investment_debate_state"]
        b_col1, b_col2 = st.columns(2)
        with b_col1: st.info("**多头观点 (Bull)**"); st.markdown(debate_state.get("bull_history", "等待发言..."))
        with b_col2: st.warning("**空头观点 (Bear)**"); st.markdown(debate_state.get("bear_history", "等待发言..."))
        if debate_state.get("judge_decision"): st.success("**决策 (研究经理):**"); st.markdown(debate_state["judge_decision"])
    else:
        st.subheader("第一阶段：分析师团队报告")
        report_keys = [("market_report", "市场分析"), ("news_report", "新闻分析"), ("sentiment_report", "社交情绪分析"), ("fundamentals_report", "基本面分析")]
        available_reports = [(key, title) for key, title in report_keys if state_chunk.get(key)]
        if available_reports:
            tab_titles = [title for _, title in available_reports]; tabs = st.tabs(tab_titles)
            for i, (key, title) in enumerate(available_reports):
                with tabs[i]: st.markdown(state_chunk[key])

def display_full_process_review(final_state):
    """(用于回顾)渲染所有分析阶段的完整顺序视图"""
    # Stage 1
    st.subheader("第一阶段：分析师团队报告")
    report_keys = [("market_report", "市场分析"), ("news_report", "新闻分析"), ("sentiment_report", "社交情绪分析"), ("fundamentals_report", "基本面分析")]
    available_reports = [(key, title) for key, title in report_keys if final_state.get(key)]
    if available_reports:
        tabs = st.tabs([title for _, title in available_reports])
        for i, (key, title) in enumerate(available_reports):
            with tabs[i]: st.markdown(final_state[key], unsafe_allow_html=True)
    st.divider()
    # Stage 2
    st.subheader("第二阶段：研究团队辩论与决策")
    if "investment_debate_state" in final_state and final_state["investment_debate_state"].get("history"):
        debate_state = final_state["investment_debate_state"]
        b_col1, b_col2 = st.columns(2)
        with b_col1: st.info("**多头观点 (Bull)**"); st.markdown(debate_state.get("bull_history", "无"), unsafe_allow_html=True)
        with b_col2: st.warning("**空头观点 (Bear)**"); st.markdown(debate_state.get("bear_history", "无"), unsafe_allow_html=True)
        if debate_state.get("judge_decision"): st.success("**决策 (研究经理):**"); st.markdown(debate_state["judge_decision"], unsafe_allow_html=True)
    st.divider()
    # Stage 3
    st.subheader("第三阶段：交易团队计划")
    if "trader_investment_plan" in final_state and final_state["trader_investment_plan"]:
        st.markdown(final_state["trader_investment_plan"], unsafe_allow_html=True)
    st.divider()
    # Stage 4/5
    st.subheader("第四/五阶段：风险管理与最终决策")
    if "risk_debate_state" in final_state and final_state["risk_debate_state"].get("history"):
        risk_state = final_state["risk_debate_state"]
        r_col1, r_col2, r_col3 = st.columns(3)
        with r_col1: st.error("**激进派观点**"); st.markdown(risk_state.get("risky_history", ""), unsafe_allow_html=True)
        with r_col2: st.info("**中立派观点**"); st.markdown(risk_state.get("neutral_history", ""), unsafe_allow_html=True)
        with r_col3: st.warning("**保守派观点**"); st.markdown(risk_state.get("safe_history", ""), unsafe_allow_html=True)
        if risk_state.get("judge_decision"): st.success("**最终决策 (投资组合经理):**"); st.markdown(risk_state["judge_decision"], unsafe_allow_html=True)

# ----- PDF 生成方案 (Playwright 同步版) -----
def generate_pdf_report(final_state, ticker, analysis_date):
    """(同步版本) 使用 sync_playwright 生成 PDF 字节流，避开 Streamlit 的 asyncio 冲突"""
    try:
        report_parts = [f"<h1>{ticker} 交易分析报告</h1>", f"<p><b>分析日期:</b> {analysis_date}</p><hr>"]
        report_keys_in_order = [("第一阶段：分析师团队报告", [("market_report", "市场分析报告"),("news_report", "新闻分析报告"),("sentiment_report", "社交情绪报告"),("fundamentals_report", "基本面分析报告")]), ("第二阶段：研究团队决策", [("investment_plan", "")]), ("第三阶段：交易团队计划", [("trader_investment_plan", "")]), ("第四/五阶段：风险管理与最终决策", [("final_trade_decision", "")])]
        for section_title, keys in report_keys_in_order:
            section_content = []
            for key, sub_title in keys:
                if final_state.get(key) and final_state[key]:
                    html_from_md = markdown2.markdown(final_state[key], extras=["tables", "fenced-code-blocks", "header-ids"])
                    if sub_title: section_content.append(f"<h3>{sub_title}</h3>{html_from_md}")
                    else: section_content.append(html_from_md)
            if section_content: report_parts.append(f"<h2>{section_title}</h2>" + "\n".join(section_content))
        html_body = "\n".join(report_parts)
        # 使用更通用的字体族以提高 PDF 兼容性
        css = """body { font-family: sans-serif; font-size: 10pt; line-height: 1.6; } h1 { font-size: 22pt; color: #1E293B; text-align: center; } h2 { font-size: 16pt; color: #334155; border-bottom: 2px solid #f1f5f9; padding-bottom: 6px; margin-top: 25px;} h3 { font-size: 13pt; color: #475569; margin-top: 20px;} table { border-collapse: collapse; width: 100%; margin-top: 15px; } th, td { border: 1px solid #e2e8f0; text-align: left; padding: 8px; } th { background-color: #f8fafc; font-weight: bold; }"""
        styled_html = f"<html><head><meta charset='UTF-8'><style>{css}</style></head><body>{html_body}</body></html>"
        
        # 使用独立的子进程生成 PDF，完美避开 Streamlit 自身隐式的 asyncio 事件循环冲突
        import subprocess
        import sys
        
        script = '''
import sys
from playwright.sync_api import sync_playwright

html = sys.stdin.read()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    pdf_bytes = page.pdf(format="A4", margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"})
    browser.close()
    sys.stdout.buffer.write(pdf_bytes)
'''
        proc = subprocess.run([sys.executable, "-c", script], input=styled_html.encode('utf-8'), capture_output=True)
        if proc.returncode != 0:
            raise Exception(proc.stderr.decode('utf-8', errors='ignore'))
        
        return proc.stdout
            
    except Exception as e:
        error_msg = f"生成 PDF 时出现错误: {str(e)}"
        raise Exception(error_msg)

# --- 主布局：顶部 Tabs（信息架构 v1.9.1）---
tab_analyze, tab_history, tab_config, tab_diagnostic = st.tabs([
    "📈 分析中心", "📚 历史分析", "⚙️ 配置", "🏥 诊断",
])

# ---- ⚙️ 配置 ----
with tab_config:
    st.header("⚙️ 配置")
    st.caption("这里是一次性配置：存储路径、LLM 提供商、API Key、模型。修改后会自动持久化到 .ui_prefs.json。")
    # --- 【新增】报告存储位置选择 ---
    st.markdown("---")
    st.subheader("存储位置")
    saved_results_dir = st.session_state.ui_prefs.get("results_dir", "./results")

    # --- 【新增】原生文件夹选择逻辑 ---
    col_path, col_btn = st.columns([3, 1])
    with col_path:
        input_results_dir = st.text_input(
            "报告保存根目录:", 
            value=saved_results_dir,
            help="分析结果（JSON 和 PDF）将存放在此目录下。支持绝对路径。"
        )
    with col_btn:
        st.write("") # 垂直对齐调整
        if st.button("📁 选择", help="弹出系统文件夹选择器"):
            try:
                folder_selected = None
                # macOS 特化处理：使用 osascript 避开线程陷阱
                if platform.system() == "Darwin":
                    script = 'POSIX path of (choose folder with prompt "请选择报告保存目录" default location POSIX file "{}")'.format(os.path.abspath(saved_results_dir))
                    proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
                    if proc.returncode == 0:
                        folder_selected = proc.stdout.strip()
                else: 
                    # 其他系统 (如 Windows)：通过子进程调用 tkinter (不会占死主线程)
                    cmd = ['python', '-c', f'import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes("-topmost", True); print(filedialog.askdirectory(initialdir="{saved_results_dir}"))']
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                    if proc.returncode == 0:
                        folder_selected = proc.stdout.strip()
                
                if folder_selected:
                    input_results_dir = folder_selected
                    update_pref("results_dir", folder_selected)
                    st.rerun()
            except Exception as e:
                st.error(f"无法启动文件夹选择器: {e}")

    if input_results_dir != saved_results_dir:
        update_pref("results_dir", input_results_dir)
        st.info("存储目录已更新，正在重新扫描历史记录...")
        st.rerun() # 立即重刷以更新 RESULTS_DIR 和扫描列表
    
    # 更新全局 RESULTS_DIR 供后续函数使用
    RESULTS_DIR = Path(input_results_dir)

    # --- UI 首选项持久化 (逻辑已上移到模块级) ---

    prov_keys = list(PROVIDER_OPTIONS.keys())
    saved_prov = st.session_state.ui_prefs.get("provider")
    prov_idx = prov_keys.index(saved_prov) if saved_prov in prov_keys else 0
    
    selected_llm_provider_name = st.selectbox("请选择 LLM 提供商:", options=prov_keys, index=prov_idx)
    if selected_llm_provider_name != saved_prov:
        update_pref("provider", selected_llm_provider_name)
        
    provider_key = selected_llm_provider_name.lower()
    pref_api_key_name = f"{provider_key}_api_key"
    saved_api_key = st.session_state.ui_prefs.get(pref_api_key_name, "")
    
    input_api_key = st.text_input(
        f"API Key (可选，将优先使用并覆盖环境变量):", 
        value=saved_api_key, 
        type="password",
        help="留空则自动读取系统环境变量中的对应 KEY"
    )
    if input_api_key != saved_api_key:
        update_pref(pref_api_key_name, input_api_key)
        
    # 【新增】保存到 .env 的功能
    env_key_map = PROVIDER_ENV_KEY_MAP
    target_env_var = env_key_map.get(selected_llm_provider_name.lower())
    
    if input_api_key and target_env_var:
        if st.button(f"💾 保存 {selected_llm_provider_name} Key 到 .env", help="持久化保存到磁盘，下次启动自动加载"):
            if update_dotenv_file(target_env_var, input_api_key):
                st.success(f"已成功将 {target_env_var} 保存到 .env！")
                st.toast("配置已持久化 💾")
        
    backend_url = PROVIDER_OPTIONS[selected_llm_provider_name]
    st.markdown("---")
    st.subheader("选择模型引擎")
    provider_key = selected_llm_provider_name.lower()
    shallow_options = SHALLOW_AGENT_OPTIONS.get(provider_key, [])
    deep_options = DEEP_AGENT_OPTIONS.get(provider_key, [])
    format_func = lambda x: x[0]

    saved_shallow = st.session_state.ui_prefs.get(f"{provider_key}_shallow")
    shallow_idx = _get_opt_idx(shallow_options, saved_shallow)
    selected_shallow_tuple = st.selectbox("快速思考引擎:", options=shallow_options, format_func=format_func, index=shallow_idx, help="用于快速、常规任务的轻量级模型")
    if selected_shallow_tuple and selected_shallow_tuple[1] != saved_shallow:
        update_pref(f"{provider_key}_shallow", selected_shallow_tuple[1])
        
    shallow_thinker = selected_shallow_tuple[1] if selected_shallow_tuple else None
    
    saved_deep = st.session_state.ui_prefs.get(f"{provider_key}_deep")
    deep_idx = _get_opt_idx(deep_options, saved_deep)
    selected_deep_tuple = st.selectbox("深度思考引擎:", options=deep_options, format_func=format_func, index=deep_idx, help="用于复杂分析和深度辩论的强大模型")
    if selected_deep_tuple and selected_deep_tuple[1] != saved_deep:
        update_pref(f"{provider_key}_deep", selected_deep_tuple[1])
        
    deep_thinker = selected_deep_tuple[1] if selected_deep_tuple else None



# --- UI 组件 (侧边栏) ---
with st.sidebar:
    st.header("分析配置")

    # Stage 7: Watchlist 快速选股
    _watchlist = st.session_state.ui_prefs.get("watchlist", [])
    if _watchlist:
        with st.expander(f"⭐ 自选股 ({len(_watchlist)})", expanded=False):
            _wl_cols = st.columns(3)
            for _i, _t in enumerate(_watchlist):
                _wl_cols[_i % 3].button(
                    _t,
                    key=f"wl_{_t}",
                    use_container_width=True,
                    on_click=lambda t=_t: st.session_state.update({"_ticker_quick": t}),
                )

    # 如果点了 watchlist 里的 ticker，用作 input 的默认值
    _ticker_default = st.session_state.pop("_ticker_quick", "")
    selected_ticker = st.text_input("请输入股票代码:", value=_ticker_default).upper()

    # 加 / 删自选股按钮
    if selected_ticker:
        _is_in_wl = selected_ticker in _watchlist
        _wl_label = "❌ 从自选股移除" if _is_in_wl else "⭐ 加入自选股"
        if st.button(_wl_label, use_container_width=True, key="wl_toggle"):
            if _is_in_wl:
                _watchlist.remove(selected_ticker)
            else:
                _watchlist.append(selected_ticker)
            update_pref("watchlist", _watchlist)
            st.rerun()
    analysis_date = st.date_input("请选择分析日期:", datetime.date.today(), max_value=datetime.date.today()).strftime("%Y-%m-%d")
    analyst_options = {"市场分析师": AnalystType.MARKET, "舆情分析师": AnalystType.SOCIAL, "新闻分析师": AnalystType.NEWS, "基本面分析师": AnalystType.FUNDAMENTALS}

    # Stage 7: 分析模板（一键应用预置参数）
    _tmpl_names = list(ANALYSIS_TEMPLATES.keys())
    _tmpl_name = st.selectbox(
        "🎨 应用模板（可选）",
        options=["—— 自定义 ——"] + _tmpl_names,
        index=0,
        help="选模板后会自动填充下面的分析师 / 研究深度 / 回溯窗口。",
    )
    _tmpl_data = ANALYSIS_TEMPLATES.get(_tmpl_name) if _tmpl_name != "—— 自定义 ——" else None
    if _tmpl_data:
        st.caption(f"📋 {_tmpl_data['description']}")

    _default_analysts = _tmpl_data["analysts"] if _tmpl_data else list(analyst_options.keys())
    selected_analyst_names = st.multiselect("请选择分析师团队:", options=list(analyst_options.keys()), default=_default_analysts)
    selected_analysts = [analyst_options[name] for name in selected_analyst_names]
    depth_options = {"极浅 - 快速总结": 0, "浅层 - 1轮辩论": 1, "中等 - 2轮辩论": 2, "深入 - 3轮辩论": 3}
    _depth_default_idx = 2
    if _tmpl_data:
        _depth_default_idx = _tmpl_data["depth"]
    selected_depth_name = st.selectbox("请选择研究深度 (轮数):", options=list(depth_options.keys()), index=_depth_default_idx)
    selected_research_depth = depth_options[selected_depth_name]

    # 【新增】回溯天数选择（模板会覆盖默认值）
    _saved_lookback = st.session_state.ui_prefs.get("lookback_days", 30)
    _lb_default = _tmpl_data["lookback_days"] if _tmpl_data else _saved_lookback
    selected_lookback_days = st.slider(
        "分析回溯窗口 (天):",
        min_value=5,
        max_value=120,
        value=_lb_default,
        help="设定 AI 分析技术指标和价格走势时向回搜索的时间范围（自然日）。"
    )
    if not _tmpl_data and selected_lookback_days != _saved_lookback:
        update_pref("lookback_days", selected_lookback_days)

    # 【新增】新闻/情绪回溯天数选择
    _saved_news_lb = st.session_state.ui_prefs.get("news_lookback_days", 7)
    _nlb_default = _tmpl_data["news_lookback_days"] if _tmpl_data else _saved_news_lb
    selected_news_lookback_days = st.slider(
        "新闻/情绪分析窗口 (天):",
        min_value=1,
        max_value=30,
        value=_nlb_default,
        help="设定 AI 分析新闻和社交媒体情绪时向回搜索的时间范围（自然日）。"
    )
    if not _tmpl_data and selected_news_lookback_days != _saved_news_lb:
        update_pref("news_lookback_days", selected_news_lookback_days)
    
    # 存储位置 / LLM 提供商 / API Key / 模型 已迁移至顶部 "⚙️ 配置" tab
    st.markdown("---")
    position_status_option = st.radio("您当前是否持有该股票？", options=["否，我没有持仓", "是，我已持有仓位"], index=0, horizontal=True)
    has_position = "已持有" if "是" in position_status_option else "未持有"
    st.markdown("---")
    
    # Stage 9: 如果当前 ticker+date 有 checkpoint，提示用户可以续跑
    if selected_ticker:
        try:
            from tradingagents.graph.checkpointer import has_checkpoint, checkpoint_step
            _data_cache = DEFAULT_CONFIG.get("data_cache_dir")
            if _data_cache and has_checkpoint(_data_cache, selected_ticker, analysis_date):
                _step = checkpoint_step(_data_cache, selected_ticker, analysis_date)
                st.info(
                    f"💾 检测到 **{selected_ticker} · {analysis_date}** 的未完成分析（步骤 {_step}），"
                    f"开启 `checkpoint_enabled` 后开始分析将自动续跑。"
                )
        except Exception:
            pass

    # 【修改】"开始分析" 前进行前置校验
    if st.button("🚀 开始分析", use_container_width=True, type="primary"):
        # 获取当前提供商对应的环境变量名
        target_env_var = env_key_map.get(selected_llm_provider_name.lower())
        # 校验：输入框有填 OR 环境变量里有
        has_key = bool(input_api_key) or (target_env_var and os.environ.get(target_env_var))
        
        if not selected_ticker:
            show_error_with_fix(
                "请先输入股票代码",
                fix_steps=[
                    "在侧边栏 **请输入股票代码** 输入框填入 ticker，例如：`NVDA`、`AAPL`、`300990.SZ`、`600519.SS`、`0700.HK`。",
                    "A 股标的会自动走中文数据源（东方财富 / 雪球 / 新浪 / akshare），美股 / 港股保持原有 Yahoo / StockTwits / Reddit 路径。",
                ],
            )
        elif not has_key:
            show_error_with_fix(
                f"缺少 {selected_llm_provider_name} 的 API Key",
                detail=f"环境变量 `{target_env_var or '???'}` 为空，且 ⚙️ 配置 tab 也未填入。",
                fix_steps=[
                    "切到顶部 **⚙️ 配置** tab，在 *API Key* 输入框填入 Key。",
                    f"点击 **💾 保存 {selected_llm_provider_name} Key 到 .env**，下次启动自动加载。",
                    f"或在终端运行 `export {target_env_var}=sk-xxx` 后重启 Streamlit。",
                ],
            )
        else:
            reset_state()
            # 针对并发模式：一开始就把所有的分析师状态设成进行中
            for name in selected_analyst_names:
                st.session_state.agent_status[name] = "in_progress"
            st.session_state.start_analysis = True
            st.session_state.has_position = has_position
            st.rerun() # 立即重跑，进入分析逻辑
        
    st.sidebar.markdown("---")
    st.sidebar.header("下载报告")
    download_placeholder = st.sidebar.empty()
    if not st.session_state.final_state:
        download_placeholder.info("分析完成后，将在此处提供下载链接。")

    # 历史记录已迁移至顶部 "📚 历史分析" tab


# --- 主布局与分析逻辑 ---

# ---- 📈 分析中心 ----
with tab_analyze:

    # 1. 分析进行中的视图
    if st.session_state.start_analysis and not st.session_state.final_state:
        progress_placeholder = st.empty()
        col1, col2 = st.columns([1, 2])
        with col1: status_placeholder = st.empty(); messages_placeholder = st.empty()
        with col2: report_placeholder = st.empty()

        if not selected_analysts:
            show_error_with_fix(
                "未选择任何分析师",
                fix_steps=[
                    "在侧边栏 **请选择分析师团队** 多选框里至少选一位。",
                    "通常 4 位全选（市场 / 舆情 / 新闻 / 基本面），决策最完整。",
                ],
            )
            st.session_state.start_analysis = False
        elif not shallow_thinker or not deep_thinker:
            show_error_with_fix(
                f"{selected_llm_provider_name} 缺少模型选择",
                detail="快速思考引擎或深度思考引擎为空。",
                fix_steps=[
                    "切到顶部 **⚙️ 配置** tab。",
                    "在 *快速思考引擎* 和 *深度思考引擎* 下拉框中各选一个模型。",
                    "推荐组合：快速 = `deepseek-v4-flash`、深度 = `deepseek-v4-pro`。",
                ],
            )
            st.session_state.start_analysis = False
        else:
            config = DEFAULT_CONFIG.copy(); 
            config.update({ 
                "max_debate_rounds": selected_research_depth, 
                "max_risk_discuss_rounds": selected_research_depth, 
                "quick_think_llm": shallow_thinker, 
                "deep_think_llm": deep_thinker, 
                "backend_url": backend_url, 
                "llm_provider": selected_llm_provider_name.lower(), 
                "api_key": str(input_api_key).strip() if input_api_key else None,
                "has_position": st.session_state.get("has_position", "未持有"),
                "results_dir": str(RESULTS_DIR), # 确保 config 中有 results_dir
                "lookback_days": selected_lookback_days,
                "news_lookback_days": selected_news_lookback_days
            })

            with st.spinner("正在初始化分析图..."):
                graph = TradingAgentsGraph([a.value for a in selected_analysts], config=config, debug=True)
                # 显式使用关键字参数，避免和 upstream 新增的 past_context
                # 位置参数串位（曾导致 lookback 设置失效）。past_context 由
                # TradingMemoryLog 在运行时填充，这里不需要预先传入。
                init_agent_state = graph.propagator.create_initial_state(
                    selected_ticker,
                    analysis_date,
                    past_context=graph.memory_log.get_past_context(selected_ticker),
                    lookback_days=selected_lookback_days,
                    news_lookback_days=selected_news_lookback_days,
                )
                args = graph.propagator.get_graph_args()



            final_chunk_for_state = None
            # 启动计时
            import time as _time
            _stream_start_ts = _time.time()
            try:
                for chunk in graph.graph.stream(init_agent_state, **args):
                    final_chunk_for_state = chunk
                    # 检测当前阶段（基于 chunk 内容推断）
                    _phase_key, _progress_pct = detect_current_phase(chunk)
                    _elapsed = _time.time() - _stream_start_ts

                    # 渲染 5 阶段 stepper（替代原来单一进度条）+ 已耗时
                    with progress_placeholder.container():
                        render_phase_stepper(_phase_key, elapsed_seconds=_elapsed)
                        st.progress(_progress_pct, text=f"总进度 {_progress_pct}%")

                    # 为下方的调试监控器预留一个循环内可更新的占位符（仅首次进入时有效）
                    if 'live_debug_placeholder' not in locals():
                        st.markdown("---")
                        live_debug_placeholder = st.empty()

                    # 【并发补单】当流中出现 report 时，代表对应分析师已跑完并发 SubGraph
                    if chunk.get("market_report"): st.session_state.agent_status["市场分析师"] = "completed"
                    if chunk.get("news_report"): st.session_state.agent_status["新闻分析师"] = "completed"
                    if chunk.get("sentiment_report"): st.session_state.agent_status["舆情分析师"] = "completed"
                    if chunk.get("fundamentals_report"): st.session_state.agent_status["基本面分析师"] = "completed"

                    # Stage 6: 累积 token 使用统计
                    _accumulate_token_stats(chunk)

                    # 将每个 agent 的最新输出记到 session_state，供下方"点击展开"显示
                    for _agent_name, _extractor in AGENT_REPORT_EXTRACTORS.items():
                        _content = _extractor(chunk)
                        if _content:
                            st.session_state.agent_reports[_agent_name] = _content

                    # 优化调试信息：仅保留关键诊断状态，防止屏幕被海量脱敏数据占满
                    st.session_state.last_chunk_raw = {
                        "当前执行节点": chunk.get("sender", "后台系统轮转"),
                        "异常中断": "无"
                    }

                    # 辩论轮数监控
                    if "risk_debate_state" in chunk:
                        count = chunk["risk_debate_state"].get("count", 0)
                        max_turns = 3 * config["max_risk_discuss_rounds"] # 3个 agent
                        st.toast(f"风险管理辩论进行中: 第 {count} / {max_turns} 次发言")

                    with status_placeholder.container():
                        st.subheader("代理状态")
                        current_sender_name = SENDER_MAP.get(chunk.get("sender"))
                        if current_sender_name and current_sender_name != st.session_state.previous_sender:
                            if st.session_state.previous_sender: st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                            st.session_state.agent_status[current_sender_name] = "in_progress"
                            st.session_state.previous_sender = current_sender_name

                        _status_label_map = {"pending": "待执行", "in_progress": "进行中", "completed": "已完成"}
                        _status_icon_map = {"pending": "⚪", "in_progress": "⏳", "completed": "✅"}

                        # 左列：紧凑状态总览（只显示状态，不展开内容；阅读区在右列 tabs 里）
                        for team, agents in TEAMS_STRUCTURE.items():
                            st.markdown(f"**🏷️ {team}**")
                            for agent in agents:
                                if not (agent in selected_analyst_names or team != "分析师团队"):
                                    continue
                                status = st.session_state.agent_status.get(agent, "pending")
                                icon = _status_icon_map.get(status, "⚪")
                                label = _status_label_map.get(status, status)
                                st.markdown(f"&emsp;{icon} {agent} · *{label}*")

                    # 右列：用 tabs 展示每个代理的输出（点击切换为客户端行为，不会触发 streamlit rerun）
                    with report_placeholder.container():
                        st.subheader("代理输出（点击上方 Tab 切换）")

                        # 按团队顺序排列 tab；只展示用户选中的分析师
                        _visible_agents = []
                        for _team, _agents in TEAMS_STRUCTURE.items():
                            for _agent in _agents:
                                if not (_agent in selected_analyst_names or _team != "分析师团队"):
                                    continue
                                _visible_agents.append(_agent)

                        if _visible_agents:
                            # tab 标签保持固定文本（不带变动的图标），避免切换造成 Streamlit 重置选中状态。
                            _tab_objs = st.tabs(_visible_agents)
                            for _tab, _agent in zip(_tab_objs, _visible_agents):
                                with _tab:
                                    _status = st.session_state.agent_status.get(_agent, "pending")
                                    _icon = _status_icon_map.get(_status, "⚪")
                                    _label = _status_label_map.get(_status, _status)
                                    st.caption(f"{_icon} 当前状态：**{_label}**")
                                    _report = st.session_state.agent_reports.get(_agent)
                                    if _report:
                                        st.markdown(_report, unsafe_allow_html=True)
                                    else:
                                        if _status == "in_progress":
                                            st.info(f"⏳ {_agent} 正在执行中，预计很快有内容...")
                                        else:
                                            st.info(f"⏸️ {_agent} 尚未开始执行")

                    with messages_placeholder.container():
                        st.subheader("消息与工具日志");
                        if "messages" in chunk and chunk["messages"]:
                            last_message = chunk["messages"][-1]; content_str = str(last_message.content) if hasattr(last_message, 'content') else ''
                            if content_str: st.session_state.messages.append(f"**思考:** {content_str[:200]}...")
                            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                                for tc in last_message.tool_calls: st.session_state.messages.append(f"**🛠️ 工具调用:** `{tc.get('name', 'N/A')}`")
                        st.markdown("\n\n".join(st.session_state.messages[-10:]))

                    # 右列已在 status_placeholder 内通过 st.tabs 展示每个代理的输出，
                    # 这里不再调用 display_live_report，避免与左列重复渲染同一份内容。

                    with live_debug_placeholder.container():
                        with st.expander("🛠️ 调试监控器 (精简版)", expanded=True):
                            status_color = "red" if st.session_state.last_chunk_raw.get("异常中断", "无") != "无" else "green"
                            st.markdown(f"**当前执行节点:** `{st.session_state.last_chunk_raw.get('当前执行节点', '正在启动...')}`")
                            st.markdown(f"**系统异常:** :{status_color}[{st.session_state.last_chunk_raw.get('异常中断', '无')}]")

                # --- 【修复】正常结束后的状态同步 ---
                if final_chunk_for_state:
                    st.session_state.final_state = final_chunk_for_state
                    # 标记最后一个运行的代理为已完成
                    if st.session_state.previous_sender: 
                        st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                    st.rerun() # 触发重绘，进入“分析完成”视图

            except Exception as e:
                if "last_chunk_raw" in st.session_state:
                    st.session_state.last_chunk_raw["异常中断"] = f"是 - {str(e)}"
                _err = str(e)
                _low_err = _err.lower()
                # 智能识别错误类型并给出有针对性的建议
                if "401" in _err or "unauthorized" in _low_err or "api key" in _low_err:
                    _fix_steps = [
                        "前往 ⚙️ 配置 tab，确认 API Key 已正确填入并保存。",
                        "在终端运行 `echo $DEEPSEEK_API_KEY` 确认环境变量也有值。",
                        "如果 key 是新申请的，等几分钟让 DeepSeek 后台同步。",
                    ]
                elif "rate limit" in _low_err or "429" in _err:
                    _fix_steps = [
                        "DeepSeek API 已触发限流。等 30-60 秒后重试。",
                        "考虑改用 `deepseek-v4-flash` 替代 `deepseek-v4-pro`，速度快、限流低。",
                    ]
                elif "connection" in _low_err or "timeout" in _low_err or "network" in _low_err:
                    _fix_steps = [
                        "检查网络连接（尤其代理是否还连得通：`curl -x $HTTPS_PROXY https://api.deepseek.com`）。",
                        "DeepSeek 的 endpoint 偶尔抽风，1-2 分钟后重试。",
                        "如果是 OpenCLI 命令失败，检查 Chrome 是否还在运行。",
                    ]
                elif "structured-output" in _low_err or "nonetype" in _low_err:
                    _fix_steps = [
                        "可能是模型不稳定地未返回结构化输出。自动回退到 free-text 应能恢复。",
                        "如反复出现，前往 ⚙️ 配置 tab 把模型切换到 `deepseek-v4-pro`（结构化输出更稳）。",
                    ]
                elif "valueerror" in _low_err and ("indicator" in _low_err or "ticker" in _low_err):
                    _fix_steps = [
                        "工具调用参数错误，重试一般能恢复。",
                        "如果是 ticker 格式问题，确认 A 股用 `300990.SZ` / `600519.SS` 格式。",
                    ]
                else:
                    _fix_steps = [
                        "展开下方『完整错误堆栈』查看具体出错位置。",
                        "前往 🏥 诊断 tab 检查依赖是否都正常。",
                        "如果反复出现，重启 Streamlit 后重试。",
                    ]

                show_error_with_fix(
                    "分析过程出错",
                    detail=f"`{_err[:200]}`" + ("..." if len(_err) > 200 else ""),
                    fix_steps=_fix_steps,
                )

                with st.expander("🔍 完整错误堆栈（点击展开）"):
                    import traceback
                    st.code(traceback.format_exc())

                st.session_state.start_analysis = False
                st.session_state.final_state = final_chunk_for_state
                if st.session_state.previous_sender:
                    st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                st.button("🔄 重置并重试", on_click=reset_state, use_container_width=True)

    # 2. 分析完成后的视图 (新分析 或 加载的历史)
    elif st.session_state.final_state:
        final_state = st.session_state.final_state

        # 从 final_state 中获取元数据
        ticker_from_state = final_state.get('company_of_interest', 'N/A')
        date_from_state = final_state.get('trade_date', 'N/A')

        st.success(f"✅ 分析完成: **{ticker_from_state}** ({date_from_state})")

        # Stage 6: 透明度卡片 — token 用量 + 数据源 + 数据新鲜度
        _ts = st.session_state.token_stats
        _fs = _format_token_stats(_ts, model=deep_thinker or "")
        with st.container(border=True):
            st.markdown("### 🔍 本次分析透明度")
            _m_cols = st.columns(5)
            _m_cols[0].metric("输入 tokens", _fs["输入 tokens"])
            _m_cols[1].metric("输出 tokens", _fs["输出 tokens"])
            _m_cols[2].metric("总 tokens", _fs["总 tokens"])
            _m_cols[3].metric("估算成本 (USD)", _fs["估算成本"])
            _m_cols[4].metric("工具调用次数", _fs["工具调用"])

            # 数据源溯源
            if _ts.get("tool_calls"):
                _tc_md = " · ".join(
                    f"`{n}`×{c}" for n, c in sorted(_ts["tool_calls"].items(), key=lambda x: -x[1])
                )
                st.caption(f"📡 数据源调用：{_tc_md}")

            # 数据新鲜度（基于 trade_date 与今日的差距）
            try:
                _trade_dt = datetime.date.fromisoformat(date_from_state)
                _delta = (datetime.date.today() - _trade_dt).days
                if _delta == 0:
                    st.caption("📅 数据新鲜度：**当日实时**")
                elif _delta <= 3:
                    st.caption(f"📅 数据新鲜度：{_delta} 天前 · 近期数据")
                else:
                    st.caption(f"📅 数据新鲜度：{_delta} 天前 · 历史回顾")
            except Exception:
                pass

        # Stage 8: 个人备注 + 快速分享
        with st.expander("📝 我的备注（点击编辑）", expanded=False):
            try:
                _existing_note = sqlite_history.get_note(RESULTS_DIR, ticker_from_state, date_from_state)
            except Exception:
                _existing_note = ""
            _note_input = st.text_area(
                "在这里记录你对本次分析的看法（保存到 SQLite，下次回看可见）",
                value=_existing_note,
                key=f"note_{ticker_from_state}_{date_from_state}",
                height=120,
            )
            _save_col, _share_col = st.columns([1, 1])
            with _save_col:
                if st.button("💾 保存备注", use_container_width=True, key="save_note_btn"):
                    try:
                        sqlite_history.set_note(RESULTS_DIR, ticker_from_state, date_from_state, _note_input)
                        st.success("✅ 备注已保存")
                    except Exception as _exc:
                        st.error(f"保存失败：{_exc}")
            with _share_col:
                # 一键生成"可分享的简报"（仅评级 + 摘要 + 备注），点击复制到 textarea
                _decision = final_state.get("final_trade_decision", "")
                _summary = (sqlite_history._extract_summary(_decision) or "（无）")[:300]
                _rating = sqlite_history._extract_rating(_decision) or "未知"
                _share_text = (
                    f"📊 TradingAgents · {ticker_from_state} · {date_from_state}\n"
                    f"评级：{_rating}\n"
                    f"摘要：{_summary}\n"
                    + (f"\n备注：{_note_input}" if _note_input else "")
                )
                if st.button("📤 生成分享简报", use_container_width=True, key="share_brief_btn"):
                    st.code(_share_text, language="markdown")
                    st.caption("👆 选中上方文本即可复制粘贴")

        st.markdown("---")

        button_text = "🙈 隐藏实时分析过程回顾" if st.session_state.show_live_report_view else "👀 显示实时分析过程回顾"
        if st.button(button_text, use_container_width=True):
            st.session_state.show_live_report_view = not st.session_state.show_live_report_view

        if st.session_state.show_live_report_view:
            with st.container(border=True):
                st.header("🕰️ 实时分析过程回顾")
                display_full_process_review(final_state)
                st.markdown("---")

        st.header("📄 完整分析报告")
        report_expanders = { "第一阶段：分析师团队报告": any(final_state.get(key) for key in ["market_report", "news_report", "sentiment_report", "fundamentals_report"]), "第二阶段：研究团队决策": bool(final_state.get("investment_plan")), "第三阶段：交易团队计划": bool(final_state.get("trader_investment_plan")), "第四/五阶段：风险管理与最终决策": bool(final_state.get("final_trade_decision")), }
        with st.expander("第一阶段：分析师团队报告", expanded=report_expanders["第一阶段：分析师团队报告"]):
            if final_state.get("market_report"): st.subheader("市场分析报告"); st.markdown(final_state["market_report"], unsafe_allow_html=True)
            if final_state.get("news_report"): st.subheader("新闻分析报告"); st.markdown(final_state["news_report"], unsafe_allow_html=True)
            if final_state.get("sentiment_report"): st.subheader("社交情绪报告"); st.markdown(final_state["sentiment_report"], unsafe_allow_html=True)
            if final_state.get("fundamentals_report"): st.subheader("基本面分析报告"); st.markdown(final_state["fundamentals_report"], unsafe_allow_html=True)
        if report_expanders["第二阶段：研究团队决策"]:
            with st.expander("第二阶段：研究团队决策", expanded=True): st.markdown(final_state["investment_plan"], unsafe_allow_html=True)
        if report_expanders["第三阶段：交易团队计划"]:
            with st.expander("第三阶段：交易团队计划", expanded=True): st.markdown(final_state["trader_investment_plan"], unsafe_allow_html=True)
        if report_expanders["第四/五阶段：风险管理与最终决策"]:
            with st.expander("第四/五阶段：风险管理与最终决策", expanded=True): st.markdown(final_state["final_trade_decision"], unsafe_allow_html=True)

        # 【修改：增强版下载按钮逻辑】
        pdf_data = st.session_state.get('pdf_data')

        if not pdf_data:
            # 1. 如果有明确路径，从磁盘加载
            if st.session_state.current_analysis_paths:
                pdf_path = Path(st.session_state.current_analysis_paths['pdf'])
                if pdf_path.exists():
                    with st.spinner(f"正在从磁盘加载报告..."):
                        with open(pdf_path, "rb") as f:
                            pdf_data = f.read()
                            st.session_state.pdf_data = pdf_data # 缓存

            # 2. 如果没有路径，但这是新分析刚跑完且 final_state 存在 (或者路径丢失了但磁盘上已有)
            if not pdf_data and st.session_state.final_state:
                # 尝试推测路径
                probable_path = RESULTS_DIR / ticker_from_state / date_from_state / "report.pdf"
                if probable_path.exists():
                    with open(probable_path, "rb") as f:
                        pdf_data = f.read()
                        st.session_state.pdf_data = pdf_data
                        st.session_state.current_analysis_paths = {
                            'json': str(probable_path.parent / "final_state_report.json"),
                            'pdf': str(probable_path)
                        }
                elif st.session_state.start_analysis:
                    # 磁盘上也没有，且是新跑完的标志，则生成
                    try:
                        with st.spinner("正在正式生成 PDF 研报... (首次运行可能较慢)"):
                            pdf_data = generate_pdf_report(final_state, ticker_from_state, date_from_state)
                            if pdf_data:
                                st.session_state.pdf_data = pdf_data
                                config_for_saving = DEFAULT_CONFIG.copy()
                                config_for_saving.update({"results_dir": str(RESULTS_DIR)})
                                save_analysis_results(final_state, ticker_from_state, date_from_state, config_for_saving, pdf_data)
                                st.success(f"💾 **PDF 及分析结果已自动保存至本地目录:** `{RESULTS_DIR / ticker_from_state / date_from_state}`")
                                st.toast("分析结果与 PDF 已自动持久化！")
                                st.session_state.start_analysis = False # 只有成功才消耗标志
                            else:
                                st.error("⚠️ PDF 字节流为空，生成失败。")
                    except Exception as e:
                        st.error(f"❌ PDF 生成失败: {e}")
                        if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
                            st.info("💡 **解决方法**: 请在终端运行 `playwright install chromium` 以安装浏览器内核。")
                        # 不消耗 start_analysis 标志，允许用户在环境修复后重试

        # 3. 渲染下载按钮或占位符
        if pdf_data:
            download_placeholder.download_button(
                label="📄 下载完整PDF报告",
                data=pdf_data,
                file_name=f"TradingAgents_Report_{ticker_from_state}_{date_from_state}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            download_placeholder.info("分析完成后，将在此处提供下载链接。")

    # 3. 初始欢迎屏幕（Stage 4：友好引导 + 最近 6 次分析 quick-access）
    else:
        with st.container(border=True):
            st.markdown("### 👋 欢迎使用 TradingAgents")
            st.markdown(
                "本框架编排 **12 个 AI 代理**（4 分析师 + 3 研究 + 1 交易员 + 4 风险）"
                "在虚拟会议室里就一个标的进行**辩论 + 投票 + 最终决策**。"
            )
            st.markdown(
                "**🚀 三步开始：**\n\n"
                "1. 在左侧侧边栏输入 **股票代码**（例如 `NVDA`、`300990.SZ`、`0700.HK`）\n"
                "2. 选择 **分析师团队**、**研究深度**、**回溯窗口** 和 **是否持有仓位**\n"
                "3. 点击 **🚀 开始分析** 按钮，然后回到这个 tab 看实时进展"
            )
            st.markdown(
                "**🆘 第一次使用？** 先去 **🏥 诊断** tab 看看依赖是否都就绪；"
                "再去 **⚙️ 配置** tab 选好 LLM 提供商和模型。"
            )

        # 最近 6 次分析快捷入口
        _recent = load_historical_analyses_cached(str(RESULTS_DIR))
        if _recent:
            st.markdown("---")
            st.markdown("### 📚 最近的分析（点击直接打开）")
            _flat = []
            for _t, _runs in _recent.items():
                for _r in _runs[:3]:  # 每个 ticker 最近 3 次
                    _flat.append({"ticker": _t, **_r})
            _flat.sort(key=lambda x: x["date"], reverse=True)
            _flat = _flat[:6]

            _cols = st.columns(3)
            for _i, _item in enumerate(_flat):
                with _cols[_i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{_item['ticker']}**")
                        st.caption(f"📅 {_item['date']}")
                        st.button(
                            "📂 查看报告",
                            key=f"recent_{_item['ticker']}_{_item['date']}",
                            on_click=load_selected_analysis,
                            args=(_item['json_path'],),
                            use_container_width=True,
                        )


# ---- 📚 历史分析 ----
with tab_history:
    st.subheader("📚 历史分析记录")
    st.caption(f"当前存储目录：`{RESULTS_DIR}`")
    # 显式调用缓存版本；2 分钟 TTL 内多次切换 tab 不会重复扫盘
    historical_analyses = load_historical_analyses_cached(str(RESULTS_DIR))

    # Stage 5：自动同步 SQLite 索引（首次进入 tab 时把磁盘的 JSON 索引进 DB）
    try:
        _new_indexed = sqlite_history.rebuild_from_disk(RESULTS_DIR)
        if _new_indexed > 0:
            st.success(f"✅ 已自动索引 {_new_indexed} 条新历史记录到 SQLite")
    except Exception as _exc:
        st.warning(f"⚠️ SQLite 索引初始化失败（不影响功能）：{_exc}")

    _db_stats = sqlite_history.stats(RESULTS_DIR)

    if not historical_analyses:
        st.info("📭 暂无历史记录。完成一次新分析后会自动出现在这里。")
    else:
        # 顶部统计行（含 SQLite 索引的评级分布）
        _total_runs = sum(len(r) for r in historical_analyses.values())
        st.markdown(
            f"📊 共 **{len(historical_analyses)}** 只标的 · "
            f"**{_total_runs}** 次历史分析"
        )
        if _db_stats["by_rating"]:
            _rating_chips = " · ".join(
                f"{r}：**{c}**" for r, c in _db_stats["by_rating"].items()
            )
            st.caption(f"评级分布：{_rating_chips}")

        # 三个功能按钮：CSV 导出 / 评级筛选 / 切换视图模式
        _bcol1, _bcol2, _bcol3 = st.columns([1, 1, 1])
        with _bcol1:
            # CSV 导出（基于 SQLite 索引）
            _csv_rows = sqlite_history.query_analyses(RESULTS_DIR)
            if _csv_rows:
                import io as _io
                import csv as _csv
                _csv_buf = _io.StringIO()
                _writer = _csv.DictWriter(
                    _csv_buf,
                    fieldnames=["ticker", "trade_date", "rating", "summary",
                                "model", "provider", "has_position", "created_at"],
                    extrasaction="ignore",
                )
                _writer.writeheader()
                for _r in _csv_rows:
                    _writer.writerow(_r)
                st.download_button(
                    "📥 导出 CSV",
                    data=_csv_buf.getvalue().encode("utf-8-sig"),
                    file_name=f"tradingagents_history_{datetime.date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with _bcol2:
            _rating_filter = st.selectbox(
                "📌 评级筛选",
                options=["全部", "Buy", "Overweight", "Hold", "Underweight", "Sell"],
                index=0,
                key="history_rating_filter",
                label_visibility="collapsed",
            )
        with _bcol3:
            _view_mode = st.selectbox(
                "👁️ 视图模式",
                options=["卡片网格", "A/B 对比"],
                index=0,
                key="history_view_mode",
                label_visibility="collapsed",
            )

        # 顶部搜索框（即时过滤）
        _filter = st.text_input(
            "🔍 按标的 / 日期搜索",
            key="history_filter",
            placeholder="例如：AAPL 或 2026-05",
        ).strip().upper()

        _sorted_tickers = sorted(historical_analyses.keys())
        if _filter:
            _sorted_tickers = [
                t for t in _sorted_tickers
                if _filter in t.upper()
                or any(_filter in r["date"] for r in historical_analyses[t])
            ]

        # 评级筛选（基于 SQLite 索引）
        _filtered_paths_by_ticker: dict[str, set] = {}
        if _rating_filter != "全部":
            _rows = sqlite_history.query_analyses(RESULTS_DIR, rating=_rating_filter)
            for _r in _rows:
                _filtered_paths_by_ticker.setdefault(_r["ticker"], set()).add(_r["trade_date"])
            _sorted_tickers = [t for t in _sorted_tickers if t in _filtered_paths_by_ticker]

        if not _sorted_tickers:
            st.warning(f"未找到匹配条件的记录。")
        elif _view_mode == "A/B 对比":
            # === A/B 对比视图：选两份分析左右对照 ===
            st.markdown("---")
            st.markdown("### 🔬 A/B 对比")
            st.caption("选择两份分析进行左右对照，便于观察同一标的不同时间，或不同标的同期。")

            # 构造所有可选项
            _ab_options = []
            for _t in _sorted_tickers:
                for _r in historical_analyses[_t]:
                    if (_rating_filter == "全部"
                        or _r["date"] in _filtered_paths_by_ticker.get(_t, set())):
                        _ab_options.append((f"{_t} · {_r['date']}", _t, _r))

            _ab_col1, _ab_col2 = st.columns(2)
            with _ab_col1:
                _sel_a = st.selectbox(
                    "左侧 A",
                    options=range(len(_ab_options)),
                    format_func=lambda i: _ab_options[i][0],
                    key="ab_sel_a",
                )
            with _ab_col2:
                _sel_b = st.selectbox(
                    "右侧 B",
                    options=range(len(_ab_options)),
                    format_func=lambda i: _ab_options[i][0],
                    index=min(1, len(_ab_options) - 1),
                    key="ab_sel_b",
                )

            # 加载两份 JSON
            def _load_json_safe(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as _f:
                        return json.load(_f)
                except Exception:
                    return {}

            _a_label, _a_ticker, _a_run = _ab_options[_sel_a]
            _b_label, _b_ticker, _b_run = _ab_options[_sel_b]
            _a_data = _load_json_safe(_a_run["json_path"])
            _b_data = _load_json_safe(_b_run["json_path"])

            _diff_col1, _diff_col2 = st.columns(2)
            for _data, _label, _col in [(_a_data, _a_label, _diff_col1),
                                          (_b_data, _b_label, _diff_col2)]:
                with _col:
                    with st.container(border=True):
                        st.markdown(f"### 📊 {_label}")
                        for _key, _title in [
                            ("market_report", "市场分析"),
                            ("news_report", "新闻分析"),
                            ("sentiment_report", "舆情分析"),
                            ("fundamentals_report", "基本面分析"),
                            ("investment_plan", "研究经理决策"),
                            ("trader_investment_plan", "交易员提案"),
                            ("final_trade_decision", "🎯 最终决策"),
                        ]:
                            _content = _data.get(_key, "")
                            if _content:
                                with st.expander(f"{_title}（{len(_content)} 字）",
                                                 expanded=(_key == "final_trade_decision")):
                                    st.markdown(_content, unsafe_allow_html=True)
        else:
            # === 卡片网格视图（默认）===
            _cols_per_row = 3
            _ticker_rows = [
                _sorted_tickers[i:i + _cols_per_row]
                for i in range(0, len(_sorted_tickers), _cols_per_row)
            ]
            for _row in _ticker_rows:
                _cols = st.columns(_cols_per_row)
                for _col, _ticker in zip(_cols, _row):
                    # 应用评级过滤
                    if _rating_filter != "全部":
                        _runs = [r for r in historical_analyses[_ticker]
                                 if r["date"] in _filtered_paths_by_ticker.get(_ticker, set())]
                    else:
                        _runs = historical_analyses[_ticker]
                    if not _runs:
                        continue
                    with _col:
                        with st.container(border=True):
                            st.markdown(f"### {_ticker}")
                            st.caption(f"{len(_runs)} 次分析")
                            for _run in _runs[:5]:  # 最多显示 5 次
                                st.button(
                                    f"📂 {_run['date']}",
                                    key=f"hist_btn_{_ticker}_{_run['date']}",
                                    on_click=load_selected_analysis,
                                    args=(_run['json_path'],),
                                    use_container_width=True,
                                )
                            if len(_runs) > 5:
                                with st.expander(f"再 {len(_runs) - 5} 次"):
                                    for _run in _runs[5:]:
                                        st.button(
                                            f"📂 {_run['date']}",
                                            key=f"hist_btn_more_{_ticker}_{_run['date']}",
                                            on_click=load_selected_analysis,
                                            args=(_run['json_path'],),
                                            use_container_width=True,
                                        )

# ---- 🏥 诊断 ----
with tab_diagnostic:
    _h_col1, _h_col2 = st.columns([4, 1])
    with _h_col1:
        st.header("🏥 系统健康检查")
        st.caption("检测各项依赖是否就绪。建议每次启动后看一眼，避免分析跑到一半才发现缺组件。结果默认缓存 5 分钟。")
    with _h_col2:
        st.write("")  # 垂直对齐
        if st.button("🔄 重新检查", help="强制重新扫描依赖（清缓存）", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # 整理检查列表
    _diag_results = []

    # 1) API Key 是否就绪
    _provider_lower = selected_llm_provider_name.lower()
    _env_var = PROVIDER_ENV_KEY_MAP.get(_provider_lower)
    _has_key = bool(input_api_key) or (_env_var and os.environ.get(_env_var))
    _diag_results.append({
        "name": f"{selected_llm_provider_name} API Key",
        "ok": bool(_has_key),
        "detail": (
            f"已从环境变量 `{_env_var}` 读取" if not input_api_key and _env_var and os.environ.get(_env_var)
            else "已在『配置』tab 输入并保存" if input_api_key
            else f"❌ 未在『配置』tab 输入，也未在 .env 中设置 `{_env_var}`"
        ),
        "fix": "前往 ⚙️ 配置 tab 填入 API Key，并点击 💾 保存到 .env" if not _has_key else None,
    })

    # 2-4) 依赖检查通过 cache_data 缓存，避免每次 rerun 都重新 import akshare/playwright
    @st.cache_data(ttl=300, show_spinner=False)
    def _diag_dependency_checks():
        """返回 (opencli_path | None, akshare_version | None, playwright_ok | error_str)"""
        import shutil as _shutil
        _opencli = _shutil.which("opencli")

        _ak_v = None
        try:
            import akshare as _ak
            _ak_v = getattr(_ak, "__version__", "?")
        except Exception:
            pass

        _pw = True
        _pw_err = ""
        try:
            from playwright.sync_api import sync_playwright as _spw  # noqa
        except Exception as _e:
            _pw = False
            _pw_err = str(_e)

        return _opencli, _ak_v, _pw, _pw_err

    _opencli_path, _ak_version, _pw_ok, _pw_err = _diag_dependency_checks()

    _diag_results.append({
        "name": "OpenCLI 浏览器桥",
        "ok": bool(_opencli_path),
        "detail": f"已安装：`{_opencli_path}`" if _opencli_path
                  else "❌ 未找到 `opencli` 命令",
        "fix": "运行 `npm install -g @jackwener/opencli` 并安装 Chrome 扩展" if not _opencli_path else None,
    })
    _diag_results.append({
        "name": "akshare 数据库",
        "ok": bool(_ak_version),
        "detail": f"已安装 v{_ak_version}" if _ak_version else "❌ 未安装",
        "fix": "运行 `pip install akshare`" if not _ak_version else None,
    })
    _diag_results.append({
        "name": "Playwright (PDF 导出)",
        "ok": _pw_ok,
        "detail": "已安装" if _pw_ok else f"❌ 未安装：{_pw_err[:80]}",
        "fix": "运行 `pip install playwright && playwright install chromium`" if not _pw_ok else None,
    })

    # 5) 结果目录可写
    try:
        _test_path = RESULTS_DIR / ".healthcheck"
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        _test_path.write_text("ok")
        _test_path.unlink()
        _dir_ok = True
        _dir_detail = f"可写：`{RESULTS_DIR}`"
    except Exception as _exc:
        _dir_ok = False
        _dir_detail = f"❌ 不可写：{_exc}"
    _diag_results.append({
        "name": "结果存储目录",
        "ok": _dir_ok,
        "detail": _dir_detail,
        "fix": "前往 ⚙️ 配置 tab 选择一个可写的目录" if not _dir_ok else None,
    })

    # 6) 当前选中模型 是否在已知 capability table
    _model_ok = bool(shallow_thinker and deep_thinker)
    _diag_results.append({
        "name": "已选 LLM 模型",
        "ok": _model_ok,
        "detail": (
            f"快速：`{shallow_thinker}`  ·  深度：`{deep_thinker}`"
            if _model_ok else "❌ 未在『配置』tab 选择模型"
        ),
        "fix": "前往 ⚙️ 配置 tab 选择 快速思考引擎 和 深度思考引擎" if not _model_ok else None,
    })

    # 渲染检查结果
    st.markdown("---")
    _ok_count = sum(1 for r in _diag_results if r["ok"])
    _total = len(_diag_results)
    if _ok_count == _total:
        st.success(f"✅ 全部 {_total} 项检查通过，可以开始分析")
    elif _ok_count >= _total * 0.6:
        st.warning(f"⚠️ {_ok_count}/{_total} 项通过，部分功能可能受限")
    else:
        st.error(f"❌ {_ok_count}/{_total} 项通过，请先修复以下问题再开始分析")

    for _r in _diag_results:
        _icon = "✅" if _r["ok"] else "❌"
        with st.container(border=True):
            st.markdown(f"### {_icon} {_r['name']}")
            st.write(_r["detail"])
            if _r.get("fix"):
                st.info(f"📌 **修复建议：** {_r['fix']}")

# --- 底部全局调试监控器 ---
st.markdown("---")
with st.expander("🛠️ 调试监控器 (精简版)", expanded=st.session_state.get("start_analysis", False)):
    if "last_chunk_raw" in st.session_state:
        status_color = "red" if st.session_state.last_chunk_raw.get("异常中断", "无") != "无" else "green"
        st.markdown(f"**当前执行节点:** `{st.session_state.last_chunk_raw.get('当前执行节点', '正在启动...')}`")
        st.markdown(f"**系统异常:** :{status_color}[{st.session_state.last_chunk_raw.get('异常中断', '无')}]")
    else:
        st.info("休眠中，等待分析指令...")