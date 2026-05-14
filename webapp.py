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
import time
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
from tradingagents.logging_config import configure_logging

# Stage 11: 初始化全局结构化日志
configure_logging()

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
    /* ── Reduce Streamlit default top padding ── */
    .block-container {
        padding-top: 1.2rem !important;
    }

    /* ── Normalize all widget labels to the same style ── */
    div[data-testid="stWidgetLabel"] p,
    div[data-testid="stWidgetLabel"] label {
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: rgba(255,255,255,0.65) !important;
        margin-bottom: 0.25rem !important;
        line-height: 1.4 !important;
    }
    /* Match custom .ta-label spans used for the 分析师 heading */
    .ta-label {
        display: block;
        font-size: 0.85rem;
        font-weight: 500;
        color: rgba(255,255,255,0.65);
        margin-bottom: 0.25rem;
        line-height: 1.4;
    }

    /* ── Tab bar ── */
    div[data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid rgba(255,255,255,0.08) !important;
        gap: 0 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        font-size: 14px !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
        padding: 10px 20px !important;
        color: rgba(255,255,255,0.45) !important;
        background: transparent !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
        transition: color 0.15s, border-color 0.15s !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:hover {
        color: rgba(255,255,255,0.75) !important;
        background: transparent !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #ffffff !important;
        background: transparent !important;
        border-bottom: 2px solid rgba(255,255,255,0.85) !important;
        font-weight: 600 !important;
    }

    /* ── Container cards ── */
    div[data-testid="stContainer"][class*="border"] {
        border-radius: 8px !important;
        border-color: rgba(255,255,255,0.1) !important;
    }

    /* ── Alert cards ── */
    div[data-testid="stAlert"] {
        border-left-width: 3px !important;
        border-radius: 6px !important;
    }

    /* ── Typography ── */
    h1 {
        padding-top: 0 !important;
        margin-bottom: 0.25rem !important;
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
    }
    h2, h3 { letter-spacing: -0.01em !important; }

    /* ── Expander ── */
    summary { font-weight: 600 !important; }

    /* ── Primary button ── */
    button[kind="primary"], button[data-testid="stBaseButton-primary"] {
        background: #16a34a !important;
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }
    button[kind="primary"]:hover {
        background: #15803d !important;
    }

    /* ── Tables ── */
    table {
        border-radius: 6px !important;
        overflow: hidden !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 主标题 + 副标题
st.title("TradingAgents")
st.caption("多代理智能交易分析框架 · v2 · A 股 / 美股 / 港股")

# Stage 9: 启动时检测降级数据源并在顶部展示 banner
_degraded = _detect_degraded_sources()
if _degraded:
    with st.container(border=True):
        st.warning(
            "⚠️ **部分数据源降级运行中**　·　不影响主流程，但相关报告会简化。"
        )
        for _reason in _degraded:
            st.caption(f"• {_reason}")
        st.caption("👉 详细诊断和修复建议见 **诊断** tab")

# --- 欢迎浮层 + 问号按钮（首次访问自动展示；问号按钮随时可再次打开）---
# HTML + CSS via st.markdown (script tags are not executed here — see components.html below)
st.markdown("""
<style>
#ta-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.72);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    z-index: 999999;
    display: flex; align-items: center; justify-content: center;
}
#ta-overlay.ta-hidden { display: none; }
#ta-modal {
    background: #111827;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 2.25rem 2.5rem 2rem;
    max-width: 560px; width: 92%;
    position: relative;
    box-shadow: 0 30px 80px rgba(0,0,0,0.6);
    animation: ta-fadein 0.2s ease;
}
@keyframes ta-fadein { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
#ta-close {
    position: absolute; top: 1rem; right: 1rem;
    width: 28px; height: 28px; border-radius: 50%;
    background: transparent;
    border: 1px solid rgba(255,255,255,0.18);
    color: rgba(255,255,255,0.55);
    font-size: 13px; cursor: pointer; line-height: 1;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s, color 0.15s;
}
#ta-close:hover { background: rgba(255,255,255,0.1); color: #fff; }
#ta-help {
    position: fixed; bottom: 1.5rem; right: 1.5rem;
    width: 36px; height: 36px; border-radius: 50%;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.14);
    color: rgba(255,255,255,0.5);
    font-size: 15px; font-weight: 600; cursor: pointer; line-height: 1;
    display: flex; align-items: center; justify-content: center;
    z-index: 99998;
    transition: background 0.15s, color 0.15s;
}
#ta-help:hover { background: rgba(255,255,255,0.14); color: #fff; }
#ta-modal h2 { margin: 0 0 0.65rem; font-size: 1.3rem; font-weight: 700; color: #fff; }
#ta-modal p  { color: rgba(255,255,255,0.72); line-height: 1.65; margin: 0 0 1rem; font-size: 0.925rem; }
#ta-modal ol { color: rgba(255,255,255,0.72); padding-left: 1.3rem; margin: 0 0 1rem; line-height: 1.9; font-size: 0.925rem; }
#ta-modal ol li strong { color: rgba(255,255,255,0.92); }
#ta-modal code { background: rgba(255,255,255,0.1); border-radius: 4px; padding: 1px 5px; font-size: 0.85rem; }
#ta-modal .ta-footer { border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.9rem; margin-top: 0.25rem; color: rgba(255,255,255,0.45); font-size: 0.82rem; line-height: 1.5; }
#ta-modal .ta-footer strong { color: rgba(255,255,255,0.65); }
</style>

<div id="ta-overlay" class="ta-hidden">
  <div id="ta-modal">
    <button id="ta-close">✕</button>
    <h2>欢迎使用 TradingAgents</h2>
    <p>
      本框架编排 <strong>12 个 AI 代理</strong>（4 分析师 + 3 研究 + 1 交易员 + 4 风险）
      在虚拟会议室里就一个标的进行<strong>辩论 + 投票 + 最终决策</strong>。
    </p>
    <p><strong style="color:rgba(255,255,255,0.9)">三步开始：</strong></p>
    <ol>
      <li>在左侧输入 <strong>股票代码</strong>（例如 <code>NVDA</code>、<code>300990.SZ</code>、<code>0700.HK</code>）</li>
      <li>选择 <strong>分析师团队</strong>、<strong>研究深度</strong>、<strong>回溯窗口</strong> 和 <strong>是否持有仓位</strong></li>
      <li>点击 <strong>开始分析</strong> 按钮，结果将在右侧实时展示</li>
    </ol>
    <div class="ta-footer">
      <strong>第一次使用？</strong> 先去 <strong>诊断</strong> tab 检查依赖是否就绪；再去 <strong>配置</strong> tab 选好 LLM 提供商和模型。
    </div>
  </div>
</div>

<button id="ta-help" title="使用帮助">?</button>
""", unsafe_allow_html=True)

# JS must run via components.html (an iframe whose script CAN execute),
# then reach into window.parent.document to wire up the overlay buttons.
_st_components.html("""
<script>
(function() {
    var doc = window.parent.document;
    var ls  = window.parent.localStorage;

    function taClose() {
        var el = doc.getElementById('ta-overlay');
        if (el) el.classList.add('ta-hidden');
        try { ls.setItem('ta_welcomed_v1', '1'); } catch(e) {}
    }
    function taOpen() {
        var el = doc.getElementById('ta-overlay');
        if (el) el.classList.remove('ta-hidden');
    }

    function init() {
        // 仅首次访问时展示
        try {
            if (!ls.getItem('ta_welcomed_v1')) {
                var el = doc.getElementById('ta-overlay');
                if (el) el.classList.remove('ta-hidden');
            }
        } catch(e) {}

        // 绑定关闭按钮
        var closeBtn = doc.getElementById('ta-close');
        if (closeBtn) { closeBtn.onclick = taClose; }

        // 点击遮罩关闭
        var overlay = doc.getElementById('ta-overlay');
        if (overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) taClose();
            });
        }

        // 绑定问号按钮
        var helpBtn = doc.getElementById('ta-help');
        if (helpBtn) { helpBtn.onclick = taOpen; }
    }

    // 等 parent DOM 就绪后执行
    if (doc.readyState === 'loading') {
        doc.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
</script>
""", height=0)

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
    "小米 MiMo (mimo)": "https://token-plan-cn.xiaomimimo.com/v1",
    "OpenAI": "https://api.openai.com/v1",
    "Google": "https://generativelen/v1",
}
PROVIDER_ENV_KEY_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "火山引擎 (volcengine)": "ARK_API_KEY",
    "小米 mimo (mimo)": "MIMO_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}
SHALLOW_AGENT_OPTIONS = {
    "deepseek": [
        ("DeepSeek V4 Flash - 最新快速模型", "deepseek-v4-flash"),
        ("DeepSeek V4 Pro - 最新旗舰模型", "deepseek-v4-pro"),
    ],
    "nvidia": [("NVIDIA-DeepSeek-V3", "deepseek-ai/deepseek-v3.2")],
    "火山引擎 (volcengine)": [("Seed-2.0", "ep-20260315170816-rdcb9")],
    "小米 mimo (mimo)": [("MiMo v2.5 Pro", "mimo-v2.5-pro")],
    "openai": [("GPT-4o mini - 快速高效", "gpt-4o-mini"), ("GPT-4o - 标准模型", "gpt-4o")],
    "google": [("Gemini 1.5 Flash - 高性价比", "gemini-1.5-flash-latest")],
}
DEEP_AGENT_OPTIONS = {
    "deepseek": [
        ("DeepSeek V4 Pro - 最新旗舰模型", "deepseek-v4-pro"),
        ("DeepSeek V4 Flash - 最新快速模型", "deepseek-v4-flash"),
    ],
    "nvidia": [("NVIDIA-DeepSeek-V3 (Thinking)", "deepseek-ai/deepseek-v3.2")],
    "火山引擎 (volcengine)": [("Seed-2.0 (Thinking)", "ep-20260315170816-rdcb9")],
    "小米 mimo (mimo)": [("MiMo v2.5 Pro", "mimo-v2.5-pro")],
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


def detect_current_phase(chunk: dict, n_analysts: int = 4,
                         analysts_done: int = 0, max_debate: int = 2) -> tuple[str, int]:
    """推断当前阶段，返回 (phase_key, progress_0_100)。
    progress 在每个阶段内线性推进：
      analysts 0-24 | research 25-49 | trader 50-54 | risk 55-79 | decision 80-100
    """
    if chunk.get("final_trade_decision"):
        return "decision", 100

    if chunk.get("risk_debate_state") and chunk["risk_debate_state"].get("history"):
        _hist = len(chunk["risk_debate_state"]["history"])
        _max  = max(max_debate * 3, 1)   # 3 agents per round
        _sub  = min(_hist / _max, 1.0)
        return "risk", int(55 + _sub * 24)

    if chunk.get("trader_investment_plan"):
        return "trader", 54

    if chunk.get("investment_plan"):
        return "research", 49

    if chunk.get("investment_debate_state") and chunk["investment_debate_state"].get("history"):
        _hist = len(chunk["investment_debate_state"]["history"])
        _max  = max(max_debate * 2, 1)   # bull + bear per round
        _sub  = min(_hist / _max, 1.0)
        return "research", int(25 + _sub * 23)

    # analyst phase — progress driven by completed analysts
    _sub = analysts_done / max(n_analysts, 1)
    return "analysts", int(_sub * 24)


def render_phase_stepper(current_phase_key: str, elapsed_seconds: float | None = None, progress_pct: int = 0):
    """渲染里程碑进度条：轨道 + 5 个节点 + 实时计时器。"""
    import time as _time_module
    phase_keys = [p["key"] for p in ANALYSIS_PHASES]
    try:
        current_idx = phase_keys.index(current_phase_key)
    except ValueError:
        current_idx = 0

    n = len(ANALYSIS_PHASES)
    # 每个节点中心在 flex 行中的百分比位置（以容器宽度为基准）
    # flex:1 × n → 第 i 个中心在 (i + 0.5) / n * 100 %
    dot_pcts = [(i + 0.5) / n * 100 for i in range(n)]
    bar_left = dot_pcts[0]      # 第一个节点中心
    bar_right = dot_pcts[-1]    # 最后一个节点中心
    bar_total = bar_right - bar_left

    # 用 progress_pct 线性插值填充宽度（超过最后节点时钳制）
    fill_width = min((progress_pct / 100) * bar_total, bar_total)

    # 生成节点 HTML
    dots_html = ""
    for i, phase in enumerate(ANALYSIS_PHASES):
        if i < current_idx:
            dot_css = "background:#22c55e;border:2px solid #22c55e;"
            symbol = "✓"; sym_css = "color:#fff;font-size:11px;font-weight:700;"
            lbl_css = "color:rgba(255,255,255,0.6);font-weight:400;"
        elif i == current_idx:
            dot_css = "background:#f7ce46;border:2px solid #f7ce46;"
            symbol = ""; sym_css = ""
            lbl_css = "color:#f7ce46;font-weight:600;"
        else:
            dot_css = "background:rgba(255,255,255,0.06);border:2px solid rgba(255,255,255,0.18);"
            symbol = ""; sym_css = ""
            lbl_css = "color:rgba(255,255,255,0.28);font-weight:400;"

        dots_html += (
            f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;">'
            f'<div style="width:22px;height:22px;border-radius:50%;{dot_css}'
            f'display:flex;align-items:center;justify-content:center;position:relative;z-index:2;">'
            f'<span style="{sym_css}">{symbol}</span></div>'
            f'<div style="font-size:11px;{lbl_css}margin-top:7px;text-align:center;white-space:nowrap;">'
            f'{phase["label"]}</div></div>'
        )

    html = f"""
<div style="position:relative;padding:10px 0 36px 0;margin:4px 0;">
  <!-- 轨道底色 -->
  <div style="position:absolute;top:20px;left:{bar_left:.2f}%;right:{100-bar_right:.2f}%;
              height:3px;background:rgba(255,255,255,0.1);border-radius:2px;z-index:0;"></div>
  <!-- 填充 -->
  <div style="position:absolute;top:20px;left:{bar_left:.2f}%;width:{fill_width:.2f}%;
              height:3px;background:#22c55e;border-radius:2px;z-index:1;transition:width .4s ease;"></div>
  <!-- 节点行 -->
  <div style="display:flex;position:relative;z-index:2;">{dots_html}</div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)

    # 实时计时器（JS setInterval，1 s 精度）
    if elapsed_seconds is not None and elapsed_seconds > 0:
        _start_ms = int((_time_module.time() - elapsed_seconds) * 1000)
        _phase_label = ANALYSIS_PHASES[current_idx]['label'] if current_idx < len(ANALYSIS_PHASES) else ""
        _st_components.html(f"""
<div id="ta-t" style="font-size:0.78rem;color:rgba(255,255,255,0.45);padding:6px 0 14px;"></div>
<script>
(function(){{
  var el=document.getElementById('ta-t');
  var s0={_start_ms}, ph={repr(_phase_label)};
  function tick(){{
    var e=Math.floor((Date.now()-s0)/1000),m=Math.floor(e/60),s=e%60;
    var t=m>0?m+' 分 '+String(s).padStart(2,'0')+' 秒':s+' 秒';
    if(el) el.textContent='⏱ 已耗时 '+t+(ph?' · '+ph:'');
  }}
  tick(); setInterval(tick,1000);
}})();
</script>
""", height=38)


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


_CUMULATIVE_STATS_FILENAME = "cumulative_stats.json"


def _cumulative_stats_path(results_dir) -> Path:
    return Path(results_dir) / _CUMULATIVE_STATS_FILENAME


def _load_cumulative_stats(results_dir) -> dict:
    """读取所有历史分析累计的 token / 成本 / 工具调用统计；缺失时返回零值。"""
    p = _cumulative_stats_path(results_dir)
    if not p.exists():
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "cost_usd": 0.0, "tool_calls": 0, "runs": 0}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 缺字段时回填零，保证旧文件向后兼容
        for k, default in (("input_tokens", 0), ("output_tokens", 0), ("total_tokens", 0),
                           ("cost_usd", 0.0), ("tool_calls", 0), ("runs", 0)):
            data.setdefault(k, default)
        return data
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "cost_usd": 0.0, "tool_calls": 0, "runs": 0}


def _accumulate_to_cumulative(results_dir, run_stats: dict, run_cost_usd: float, run_id: str) -> None:
    """把单次分析的 stats 追加到累计文件；通过 session_state 的 run_id 去重，避免 rerun 时重复累加。"""
    accumulated_key = "_cumulative_accumulated_run_id"
    if st.session_state.get(accumulated_key) == run_id:
        return  # 同一次运行已经计过了
    cum = _load_cumulative_stats(results_dir)
    cum["input_tokens"]  += int(run_stats.get("input_tokens", 0) or 0)
    cum["output_tokens"] += int(run_stats.get("output_tokens", 0) or 0)
    cum["total_tokens"]  += int(run_stats.get("total_tokens", 0) or 0)
    cum["cost_usd"]      += float(run_cost_usd or 0.0)
    cum["tool_calls"]    += int(sum((run_stats.get("tool_calls") or {}).values()))
    cum["runs"]          += 1
    try:
        _cumulative_stats_path(results_dir).parent.mkdir(parents=True, exist_ok=True)
        with open(_cumulative_stats_path(results_dir), "w", encoding="utf-8") as f:
            json.dump(cum, f, ensure_ascii=False, indent=2)
        st.session_state[accumulated_key] = run_id
    except Exception:
        pass


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
        "_cost_usd_raw": cost_usd,
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
    """加载选定的历史 JSON 文件到 session_state，并跳转到分析中心 tab"""
    reset_state()
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
        st.session_state._jump_to_analyze_tab = True   # 触发 JS tab 切换
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
        with r_col1: st.error("**激进派观点**"); st.markdown(risk_state.get("aggressive_history", ""))
        with r_col2: st.info("**中立派观点**"); st.markdown(risk_state.get("neutral_history", ""))
        with r_col3: st.warning("**保守派观点**"); st.markdown(risk_state.get("conservative_history", ""))
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
        with r_col1: st.error("**激进派观点**"); st.markdown(risk_state.get("aggressive_history", ""), unsafe_allow_html=True)
        with r_col2: st.info("**中立派观点**"); st.markdown(risk_state.get("neutral_history", ""), unsafe_allow_html=True)
        with r_col3: st.warning("**保守派观点**"); st.markdown(risk_state.get("conservative_history", ""), unsafe_allow_html=True)
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
    "分析中心", "历史分析", "配置", "诊断",
])

# 历史记录加载后自动跳转到「分析中心」tab（JS 点击第一个 tab）
if st.session_state.pop("_jump_to_analyze_tab", False):
    _st_components.html("""
<script>
(function(){
  function switchTab(){
    var tabs=window.parent.document.querySelectorAll('div[data-testid="stTabs"] button[role="tab"]');
    if(tabs.length>0){ tabs[0].click(); return true; }
    return false;
  }
  if(!switchTab()){ setTimeout(switchTab,300); }
})();
</script>
""", height=0)

# ---- 配置 ----
with tab_config:
    st.header("配置")
    st.caption("这里是一次性配置：存储路径、LLM 提供商、API Key、模型。修改后会自动持久化到 .ui_prefs.json。")
    # --- 【新增】报告存储位置选择 ---
    st.markdown("---")
    st.subheader("存储位置")
    saved_results_dir = st.session_state.ui_prefs.get("results_dir", "./results")

    # --- 【新增】原生文件夹选择逻辑 ---
    col_path, col_btn = st.columns([3, 1], vertical_alignment="bottom")
    with col_path:
        input_results_dir = st.text_input(
            "报告保存根目录:",
            value=saved_results_dir,
            help="分析结果（JSON 和 PDF）将存放在此目录下。支持绝对路径。"
        )
    with col_btn:
        if st.button("📁 选择", help="弹出系统文件夹选择器", use_container_width=True):
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
    
    # ── LLM 提供商 · API Key · 保存按钮（同一行）────────────────────────────
    _cfg_r1_prov, _cfg_r1_key, _cfg_r1_btn = st.columns([1.4, 3, 1.4], vertical_alignment="bottom")

    with _cfg_r1_prov:
        st.markdown('<span class="ta-label">LLM 提供商</span>', unsafe_allow_html=True)
        selected_llm_provider_name = st.selectbox(
            "LLM 提供商", options=prov_keys, index=prov_idx,
            label_visibility="collapsed",
        )
        if selected_llm_provider_name != saved_prov:
            update_pref("provider", selected_llm_provider_name)

    provider_key = selected_llm_provider_name.lower()
    pref_api_key_name = f"{provider_key}_api_key"
    saved_api_key = st.session_state.ui_prefs.get(pref_api_key_name, "")

    with _cfg_r1_key:
        st.markdown('<span class="ta-label">API Key</span>', unsafe_allow_html=True)
        input_api_key = st.text_input(
            "API Key", value=saved_api_key, type="password",
            placeholder="留空则自动读取系统环境变量",
            label_visibility="collapsed",
        )
        if input_api_key != saved_api_key:
            update_pref(pref_api_key_name, input_api_key)

    env_key_map = PROVIDER_ENV_KEY_MAP
    target_env_var = env_key_map.get(selected_llm_provider_name.lower())

    with _cfg_r1_btn:
        st.markdown('<span class="ta-label">&nbsp;</span>', unsafe_allow_html=True)
        if input_api_key and target_env_var:
            if st.button(f"💾 保存到 .env", use_container_width=True,
                         help="持久化保存到磁盘，下次启动自动加载"):
                if update_dotenv_file(target_env_var, input_api_key):
                    st.success(f"已保存 {target_env_var} 到 .env")
                    st.toast("配置已持久化 💾")
        else:
            st.button("💾 保存到 .env", use_container_width=True, disabled=True)

    backend_url = PROVIDER_OPTIONS[selected_llm_provider_name]
    st.markdown("---")
    st.subheader("选择模型引擎")

    # ── 快速思考引擎 · 深度思考引擎（同一行）────────────────────────────────
    provider_key = selected_llm_provider_name.lower()
    shallow_options = SHALLOW_AGENT_OPTIONS.get(provider_key, [])
    deep_options = DEEP_AGENT_OPTIONS.get(provider_key, [])
    format_func = lambda x: x[0]

    _cfg_r2_shallow, _cfg_r2_deep = st.columns(2)

    with _cfg_r2_shallow:
        saved_shallow = st.session_state.ui_prefs.get(f"{provider_key}_shallow")
        shallow_idx = _get_opt_idx(shallow_options, saved_shallow)
        selected_shallow_tuple = st.selectbox(
            "快速思考引擎", options=shallow_options, format_func=format_func,
            index=shallow_idx, help="用于快速、常规任务的轻量级模型",
        )
        if selected_shallow_tuple and selected_shallow_tuple[1] != saved_shallow:
            update_pref(f"{provider_key}_shallow", selected_shallow_tuple[1])
    shallow_thinker = selected_shallow_tuple[1] if selected_shallow_tuple else None

    with _cfg_r2_deep:
        saved_deep = st.session_state.ui_prefs.get(f"{provider_key}_deep")
        deep_idx = _get_opt_idx(deep_options, saved_deep)
        selected_deep_tuple = st.selectbox(
            "深度思考引擎", options=deep_options, format_func=format_func,
            index=deep_idx, help="用于复杂分析和深度辩论的强大模型",
        )
        if selected_deep_tuple and selected_deep_tuple[1] != saved_deep:
            update_pref(f"{provider_key}_deep", selected_deep_tuple[1])
    deep_thinker = selected_deep_tuple[1] if selected_deep_tuple else None



# ---- 分析中心 ----
with tab_analyze:
    analyst_options = {"市场分析师": AnalystType.MARKET, "舆情分析师": AnalystType.SOCIAL, "新闻分析师": AnalystType.NEWS, "基本面分析师": AnalystType.FUNDAMENTALS}
    _watchlist = st.session_state.ui_prefs.get("watchlist", [])

    # 自选股快捷入口
    if _watchlist:
        _wl_pill_cols = st.columns(min(len(_watchlist), 6))
        for _i, _t in enumerate(_watchlist[:6]):
            _wl_pill_cols[_i].button(
                _t, key=f"wl_{_t}", use_container_width=True,
                on_click=lambda t=_t: st.session_state.update({"_ticker_quick": t}),
            )

    # ── 第一行：股票代码 · 已持有仓位 · 开始分析 ──────────────────────────────
    _ticker_default = st.session_state.pop("_ticker_quick", "")
    _row1_ticker, _row1_pos, _row1_btn = st.columns([4, 1.2, 1.8], vertical_alignment="center")

    with _row1_ticker:
        _tc, _wc = st.columns([6, 1])
        with _tc:
            selected_ticker = st.text_input(
                "股票代码", value=_ticker_default,
                placeholder="NVDA / 300990.SZ / 0700.HK",
                label_visibility="collapsed",
            ).upper()
        with _wc:
            if selected_ticker:
                _is_in_wl = selected_ticker in _watchlist
                if st.button(
                    "★" if not _is_in_wl else "✕",
                    key="wl_toggle", use_container_width=True,
                    help="加入自选股" if not _is_in_wl else "移除自选股",
                ):
                    if _is_in_wl:
                        _watchlist.remove(selected_ticker)
                    else:
                        _watchlist.append(selected_ticker)
                    update_pref("watchlist", _watchlist)
                    st.rerun()
        if selected_ticker:
            @st.cache_data(ttl=60, show_spinner=False)
            def _live_quote(ticker: str) -> dict | None:
                import subprocess as _sub, shutil as _sh
                if not _sh.which("opencli"):
                    return None
                try:
                    from tradingagents.dataflows.xueqiu import to_xueqiu_symbol
                    symbol = to_xueqiu_symbol(ticker)
                except Exception:
                    symbol = ticker
                try:
                    proc = _sub.run(["opencli", "xueqiu", "stock", symbol, "-f", "json"],
                                    capture_output=True, text=True, timeout=8)
                    if proc.returncode == 0 and proc.stdout:
                        data = json.loads(proc.stdout)
                        if isinstance(data, list) and data:
                            return data[0]
                        if isinstance(data, dict):
                            return data
                except Exception:
                    pass
                return None
            _quote = _live_quote(selected_ticker)
            if _quote:
                _price   = _quote.get("price")
                _name    = _quote.get("name", "")
                _chg_pct = _quote.get("changePercent", "")
                _is_up   = isinstance(_quote.get("change"), (int, float)) and _quote["change"] >= 0
                _clr     = "#22c55e" if _is_up else "#ef4444"
                _arrow   = "↑" if _is_up else "↓"
                st.markdown(
                    f'<div style="display:flex;align-items:baseline;gap:0.4rem;margin:0.1rem 0 0;">'
                    f'<span style="font-size:0.85rem;font-weight:600">{_name or selected_ticker}</span>'
                    f'<span style="font-size:0.95rem;font-weight:700">{_price or "—"}</span>'
                    f'<span style="color:{_clr};font-size:0.8rem">{_arrow} {_chg_pct}</span>'
                    f'</div>', unsafe_allow_html=True,
                )

    with _row1_pos:
        _pos_toggle = st.toggle("已持有仓位")
        has_position = "已持有" if _pos_toggle else "未持有"

    with _row1_btn:
        try:
            _btn_provider = st.session_state.ui_prefs.get("provider", "DeepSeek")
            _btn_label = f"开始分析 · {_btn_provider}"
        except Exception:
            _btn_label = "开始分析"
        _do_start = st.button(_btn_label, use_container_width=True, type="primary")

    # ── 第二行：分析日期 · 分析师(checkbox) · 研究深度 ────────────────────────
    _row2_date, _row2_ana, _row2_dep = st.columns([1.4, 3, 2.8])

    with _row2_date:
        st.markdown('<span class="ta-label">分析日期</span>', unsafe_allow_html=True)
        analysis_date = st.date_input(
            "分析日期", datetime.date.today(), max_value=datetime.date.today(),
            label_visibility="collapsed",
        ).strftime("%Y-%m-%d")

    with _row2_ana:
        _tmpl_data = None  # 模板功能已移除
        st.markdown('<span class="ta-label">分析师</span>', unsafe_allow_html=True)
        _ana_cols = st.columns(4)
        _analyst_keys = list(analyst_options.keys())
        selected_analyst_names = [
            name for name, col in zip(_analyst_keys, _ana_cols)
            if col.checkbox(name, value=True, key=f"ana_{name}")
        ]
        selected_analysts = [analyst_options[n] for n in selected_analyst_names]

    with _row2_dep:
        _depth_labels = ["极浅", "浅层", "中等", "深入"]
        _depth_values = {"极浅": 0, "浅层": 1, "中等": 2, "深入": 3}
        _saved_depth  = st.session_state.ui_prefs.get("research_depth", 2)
        st.markdown('<span class="ta-label">研究深度</span>', unsafe_allow_html=True)
        _depth_name = st.radio(
            "研究深度", options=_depth_labels, index=_saved_depth,
            horizontal=True, help="极浅=快速总结  浅层=1轮辩论  中等=2轮辩论  深入=3轮辩论",
            label_visibility="collapsed",
        )
        selected_research_depth = _depth_values[_depth_name]
        if selected_research_depth != _saved_depth:
            update_pref("research_depth", selected_research_depth)

    # ── 第三行：价格回溯 · 新闻回溯 ──────────────────────────────────────────
    _row3_lb, _row3_nlb = st.columns(2)

    with _row3_lb:
        _saved_lookback = st.session_state.ui_prefs.get("lookback_days", 30)
        selected_lookback_days = st.slider(
            "价格回溯 (天)", min_value=5, max_value=120, value=_saved_lookback,
            help="AI 分析技术指标时向前搜索的交易日范围。",
        )
        if selected_lookback_days != _saved_lookback:
            update_pref("lookback_days", selected_lookback_days)

    with _row3_nlb:
        _saved_news_lb = st.session_state.ui_prefs.get("news_lookback_days", 7)
        selected_news_lookback_days = st.slider(
            "新闻回溯 (天)", min_value=1, max_value=30, value=_saved_news_lb,
            help="AI 分析新闻和社交情绪时向前搜索的自然日范围。",
        )
        if selected_news_lookback_days != _saved_news_lb:
            update_pref("news_lookback_days", selected_news_lookback_days)

    # Checkpoint 提示
    if selected_ticker:
        try:
            from tradingagents.graph.checkpointer import has_checkpoint, checkpoint_step
            _data_cache = DEFAULT_CONFIG.get("data_cache_dir")
            if _data_cache and has_checkpoint(_data_cache, selected_ticker, analysis_date):
                _step = checkpoint_step(_data_cache, selected_ticker, analysis_date)
                st.caption(f"检测到未完成分析（步骤 {_step}），开启 checkpoint 后将自动续跑。")
        except Exception:
            pass

    # ── 第四行：分析完成后显示下载链接 ───────────────────────────────────────
    download_placeholder = st.empty()
    if st.session_state.final_state:
        pass  # 下载按钮由下方结果区域填充

    if _do_start:
        target_env_var = env_key_map.get(selected_llm_provider_name.lower())
        has_key = bool(input_api_key) or (target_env_var and os.environ.get(target_env_var))
        if not selected_ticker:
            show_error_with_fix(
                "请先输入股票代码",
                fix_steps=[
                    "在上方 **股票代码** 输入框填入 ticker，例如：`NVDA`、`AAPL`、`300990.SZ`、`600519.SS`、`0700.HK`。",
                    "A 股标的会自动走中文数据源（东方财富 / 雪球 / 新浪 / akshare），美股 / 港股保持原有 Yahoo / StockTwits / Reddit 路径。",
                ],
            )
        elif not has_key:
            show_error_with_fix(
                f"缺少 {selected_llm_provider_name} 的 API Key",
                detail=f"环境变量 `{target_env_var or '???'}` 为空，且 配置 tab 也未填入。",
                fix_steps=[
                    "切到顶部 **配置** tab，在 *API Key* 输入框填入 Key。",
                    f"点击 **💾 保存 {selected_llm_provider_name} Key 到 .env**，下次启动自动加载。",
                    f"或在终端运行 `export {target_env_var}=sk-xxx` 后重启 Streamlit。",
                ],
            )
        else:
            reset_state()
            for name in selected_analyst_names:
                st.session_state.agent_status[name] = "in_progress"
            st.session_state.start_analysis = True
            st.session_state.has_position = has_position
            st.rerun()

    st.divider()

    # ── 结果区域（全宽）─────────────────────────────────────────────────────
    # 1. 分析进行中的视图
    if st.session_state.start_analysis and not st.session_state.final_state:
        progress_placeholder = st.empty()
        report_placeholder = st.empty()

        if not selected_analysts:
            show_error_with_fix(
                "未选择任何分析师",
                fix_steps=[
                    "在左侧 **请选择分析师团队** 多选框里至少选一位。",
                    "通常 4 位全选（市场 / 舆情 / 新闻 / 基本面），决策最完整。",
                ],
            )
            st.session_state.start_analysis = False
        elif not shallow_thinker or not deep_thinker:
            show_error_with_fix(
                f"{selected_llm_provider_name} 缺少模型选择",
                detail="快速思考引擎或深度思考引擎为空。",
                fix_steps=[
                    "切到顶部 **配置** tab。",
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
            _stream_start_ts = time.time()
            try:
                for chunk in graph.graph.stream(init_agent_state, **args):
                    final_chunk_for_state = chunk

                    # ── 先更新 agent 状态，再计算进度 ────────────────────────────
                    if chunk.get("market_report"):      st.session_state.agent_status["市场分析师"] = "completed"
                    if chunk.get("news_report"):        st.session_state.agent_status["新闻分析师"] = "completed"
                    if chunk.get("sentiment_report"):   st.session_state.agent_status["舆情分析师"] = "completed"
                    if chunk.get("fundamentals_report"):st.session_state.agent_status["基本面分析师"] = "completed"

                    _analysts_done = sum(
                        1 for n in selected_analyst_names
                        if st.session_state.agent_status.get(n) == "completed"
                    )
                    _phase_key, _progress_pct = detect_current_phase(
                        chunk,
                        n_analysts=max(len(selected_analyst_names), 1),
                        analysts_done=_analysts_done,
                        max_debate=selected_research_depth,
                    )
                    _elapsed = time.time() - _stream_start_ts

                    # 渲染里程碑进度条 + 实时计时器
                    with progress_placeholder.container():
                        render_phase_stepper(_phase_key, elapsed_seconds=_elapsed, progress_pct=_progress_pct)

                    # 为下方的调试监控器预留一个循环内可更新的占位符（仅首次进入时有效）
                    if 'live_debug_placeholder' not in locals():
                        st.markdown("---")
                        live_debug_placeholder = st.empty()

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

                    # 更新当前发言代理的状态（状态直接体现在下方 tab 标签上）
                    current_sender_name = SENDER_MAP.get(chunk.get("sender"))
                    if current_sender_name and current_sender_name != st.session_state.previous_sender:
                        if st.session_state.previous_sender: st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                        st.session_state.agent_status[current_sender_name] = "in_progress"
                        st.session_state.previous_sender = current_sender_name

                    _status_label_map = {"pending": "待执行", "in_progress": "进行中", "completed": "已完成"}
                    _status_icon_map = {"pending": "⚪", "in_progress": "⏳", "completed": "✅"}

                    # 用 tabs 展示每个代理的输出（点击切换为客户端行为，不会触发 streamlit rerun）
                    with report_placeholder.container():
                        # 按团队顺序排列 tab；只展示用户选中的分析师
                        _visible_agents = []
                        for _team, _agents in TEAMS_STRUCTURE.items():
                            for _agent in _agents:
                                if not (_agent in selected_analyst_names or _team != "分析师团队"):
                                    continue
                                _visible_agents.append(_agent)

                        if _visible_agents:
                            # 自包含 JS 竖向 tab 组件 — 纯客户端切换，不触发 Streamlit rerun
                            # tab 选中状态通过 localStorage 在 chunk 重渲染间持久化
                            _agents_data = []
                            for _a in _visible_agents:
                                _s = st.session_state.agent_status.get(_a, "pending")
                                _ico = _status_icon_map.get(_s, "⚪")
                                _lbl = _status_label_map.get(_s, _s)
                                _rpt = st.session_state.agent_reports.get(_a, "")
                                _rpt_html = markdown2.markdown(_rpt, extras=["tables","fenced-code-blocks"]) if _rpt else ""
                                _agents_data.append({
                                    "name": _a, "icon": _ico, "label": _lbl,
                                    "html": _rpt_html, "status": _s,
                                })
                            _agents_json = json.dumps(_agents_data, ensure_ascii=False)

                            _tab_component = f"""
<style>
body{{margin:0;background:transparent;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:rgba(255,255,255,0.9);}}
.wrap{{display:flex;gap:0;min-height:120px;}}
.nav{{width:148px;flex-shrink:0;padding-right:12px;border-right:1px solid rgba(255,255,255,0.08);}}
.ni{{padding:6px 10px;margin-bottom:3px;border-radius:6px;font-size:13px;cursor:pointer;
     border-left:3px solid transparent;color:rgba(255,255,255,0.5);user-select:none;transition:all .15s;}}
.ni:hover{{color:rgba(255,255,255,0.8);background:rgba(255,255,255,0.05);}}
.ni.active{{background:rgba(255,255,255,0.09);border-left-color:#fff;color:#fff;font-weight:600;}}
.content{{flex:1;padding-left:16px;overflow:auto;max-height:600px;}}
.panel{{display:none;font-size:13.5px;line-height:1.75;}}
.panel.active{{display:block;}}
.panel p{{margin:.4em 0;}}
.panel h1,.panel h2,.panel h3{{color:#fff;margin:.9em 0 .3em;font-weight:600;}}
.panel table{{border-collapse:collapse;width:100%;margin:.5em 0;}}
.panel th,.panel td{{border:1px solid rgba(255,255,255,0.13);padding:5px 10px;}}
.panel th{{background:rgba(255,255,255,0.07);}}
.panel code{{background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:3px;font-size:12px;}}
.status-lbl{{font-size:11.5px;color:rgba(255,255,255,0.42);margin-bottom:10px;}}
.placeholder{{color:rgba(255,255,255,0.35);font-size:13px;padding:12px 0;}}
</style>
<div class="wrap">
  <div class="nav" id="nav"></div>
  <div class="content" id="content"></div>
</div>
<script>
var agents={_agents_json};
var LS_KEY='ta_agent_tab';
var cur=Math.min(parseInt(localStorage.getItem(LS_KEY)||'0'),agents.length-1);
function render(){{
  var nav=document.getElementById('nav');
  var cnt=document.getElementById('content');
  nav.innerHTML=''; cnt.innerHTML='';
  agents.forEach(function(a,i){{
    var d=document.createElement('div');
    d.className='ni'+(i===cur?' active':'');
    d.textContent=a.icon+' '+a.name;
    d.onclick=(function(idx){{return function(){{cur=idx;localStorage.setItem(LS_KEY,idx);render();}}}})(i);
    nav.appendChild(d);
    var p=document.createElement('div');
    p.className='panel'+(i===cur?' active':'');
    var body='<div class="status-lbl">'+a.icon+' '+a.name+' · '+a.label+'</div>';
    if(a.html){{body+=a.html;}}
    else if(a.status==='in_progress'){{body+='<div class="placeholder">⏳ 正在执行中，预计很快有内容…</div>';}}
    else{{body+='<div class="placeholder">⏸️ 尚未开始执行</div>';}}
    p.innerHTML=body;
    cnt.appendChild(p);
  }});
}}
render();
</script>
"""
                            _st_components.html(_tab_component, height=640, scrolling=False)

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
                        "前往 配置 tab，确认 API Key 已正确填入并保存。",
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
                        "如反复出现，前往 配置 tab 把模型切换到 `deepseek-v4-pro`（结构化输出更稳）。",
                    ]
                elif "valueerror" in _low_err and ("indicator" in _low_err or "ticker" in _low_err):
                    _fix_steps = [
                        "工具调用参数错误，重试一般能恢复。",
                        "如果是 ticker 格式问题，确认 A 股用 `300990.SZ` / `600519.SS` 格式。",
                    ]
                else:
                    _fix_steps = [
                        "展开下方『完整错误堆栈』查看具体出错位置。",
                        "前往 诊断 tab 检查依赖是否都正常。",
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
            st.markdown("### 本次分析透明度")
            _m_cols = st.columns(5)
            _m_cols[0].metric("输入 tokens", _fs["输入 tokens"])
            _m_cols[1].metric("输出 tokens", _fs["输出 tokens"])
            _m_cols[2].metric("总 tokens", _fs["总 tokens"])
            _m_cols[3].metric("估算成本 (USD)", _fs["估算成本"])
            _m_cols[4].metric("工具调用次数", _fs["工具调用"])

            # 累计到持久化文件（用 ticker+date 作为 run_id 去重，避免 rerun 时重复累加）
            _accumulate_to_cumulative(
                RESULTS_DIR, _ts, _fs.get("_cost_usd_raw", 0.0),
                run_id=f"{ticker_from_state}_{date_from_state}",
            )

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
                st.header("实时分析过程回顾")
                display_full_process_review(final_state)
                st.markdown("---")

        st.header("完整分析报告")

        # 分析师报告：左侧竖向 tab 导航（纯 CSS + st.tabs 内容，不会重启流）
        _fs_analyst_reports = [
            ("market_report", "市场分析"),
            ("news_report", "新闻分析"),
            ("sentiment_report", "情绪分析"),
            ("fundamentals_report", "基本面"),
        ]
        _fs_avail = [(k, t) for k, t in _fs_analyst_reports if final_state.get(k)]
        if _fs_avail:
            _fs_nav_col, _fs_content_col = st.columns([1, 4])
            with _fs_nav_col:
                _fs_sel = st.radio(
                    "分析师报告", options=[t for _, t in _fs_avail],
                    label_visibility="collapsed", key="fs_analyst_nav",
                )
            with _fs_content_col:
                _fs_key = {t: k for k, t in _fs_avail}[_fs_sel]
                st.markdown(final_state[_fs_key], unsafe_allow_html=True)

        if final_state.get("investment_plan"):
            with st.expander("研究团队决策", expanded=True):
                st.markdown(final_state["investment_plan"], unsafe_allow_html=True)
        if final_state.get("trader_investment_plan"):
            with st.expander("交易团队计划", expanded=True):
                st.markdown(final_state["trader_investment_plan"], unsafe_allow_html=True)
        if final_state.get("final_trade_decision"):
            with st.expander("风险管理与最终决策", expanded=True):
                st.markdown(final_state["final_trade_decision"], unsafe_allow_html=True)

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

    # 3. 空闲状态（欢迎引导已移至浮层，历史记录见「历史分析」tab）
    else:
        pass


# ---- 📚 历史分析 ----
with tab_history:
    st.subheader("历史分析记录")
    st.caption(f"当前存储目录：`{RESULTS_DIR}`")

    # 累计统计总览（覆盖所有历史分析）
    _cum = _load_cumulative_stats(RESULTS_DIR)
    with st.container(border=True):
        st.markdown("### 累计统计（所有分析）")
        _cum_cols = st.columns(5)
        _cum_cols[0].metric("输入 tokens", f"{_cum['input_tokens']:,}")
        _cum_cols[1].metric("输出 tokens", f"{_cum['output_tokens']:,}")
        _cum_cols[2].metric("总 tokens",   f"{_cum['total_tokens']:,}")
        _cum_cols[3].metric("估算成本 (USD)",
                            f"${_cum['cost_usd']:.4f}" if _cum["cost_usd"] > 0 else "—")
        _cum_cols[4].metric("工具调用次数", f"{_cum['tool_calls']:,}")
        st.caption(f"📁 来源：{_cum['runs']} 次分析累计 · 数据存于 `{_CUMULATIVE_STATS_FILENAME}`")

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
            _rating_cn = {"Buy": "买入", "Overweight": "增持", "Hold": "持有",
                          "Underweight": "减持", "Sell": "卖出", "Unknown": "未知"}
            _rating_chips = " · ".join(
                f"{_rating_cn.get(r, r)}：**{c}**" for r, c in _db_stats["by_rating"].items()
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
            _rating_label_map = {
                "全部": "全部",
                "Buy": "买入",
                "Overweight": "增持",
                "Hold": "持有",
                "Underweight": "减持",
                "Sell": "卖出",
            }
            _rating_filter = st.selectbox(
                "📌 评级筛选",
                options=list(_rating_label_map.keys()),
                index=0,
                key="history_rating_filter",
                label_visibility="collapsed",
                format_func=lambda x: _rating_label_map[x],
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
            st.markdown("### A/B 对比")
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
                        st.markdown(f"### {_label}")
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
            _cols_per_row = 5
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

# ---- 诊断 ----
with tab_diagnostic:
    _h_col1, _h_col2 = st.columns([4, 1])
    with _h_col1:
        st.header("系统健康检查")
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
        "fix": "前往 配置 tab 填入 API Key，并点击 保存到 .env" if not _has_key else None,
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
        "fix": "前往 配置 tab 选择一个可写的目录" if not _dir_ok else None,
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
        "fix": "前往 配置 tab 选择 快速思考引擎 和 深度思考引擎" if not _model_ok else None,
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

    _diag_cols = st.columns(3)
    for _i, _r in enumerate(_diag_results):
        _icon = "✅" if _r["ok"] else "❌"
        with _diag_cols[_i % 3]:
            with st.container(border=True):
                st.markdown(f"**{_icon} {_r['name']}**")
                st.caption(_r["detail"])
                if _r.get("fix"):
                    st.info(f"**修复建议：** {_r['fix']}")

