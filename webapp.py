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

st.title("📈 TradingAgents: 智能交易分析框架")

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

# 【新增】加载历史记录的函数
def load_historical_analyses(base_dir):
    """扫描结果目录并返回一个按 Ticker 分组的字典"""
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
    selected_ticker = st.text_input("请输入股票代码:", value="").upper()
    analysis_date = st.date_input("请选择分析日期:", datetime.date.today(), max_value=datetime.date.today()).strftime("%Y-%m-%d")
    analyst_options = {"市场分析师": AnalystType.MARKET, "舆情分析师": AnalystType.SOCIAL, "新闻分析师": AnalystType.NEWS, "基本面分析师": AnalystType.FUNDAMENTALS}
    selected_analyst_names = st.multiselect("请选择分析师团队:", options=list(analyst_options.keys()), default=list(analyst_options.keys()))
    selected_analysts = [analyst_options[name] for name in selected_analyst_names]
    depth_options = {"极浅 - 快速总结": 0, "浅层 - 1轮辩论": 1, "中等 - 2轮辩论": 2, "深入 - 3轮辩论": 3}
    selected_depth_name = st.selectbox("请选择研究深度 (轮数):", options=list(depth_options.keys()), index=2)
    selected_research_depth = depth_options[selected_depth_name]

    # 【新增】回溯天数选择
    saved_lookback = st.session_state.ui_prefs.get("lookback_days", 30)
    selected_lookback_days = st.slider(
        "分析回溯窗口 (天):", 
        min_value=5, 
        max_value=120, 
        value=saved_lookback,
        help="设定 AI 分析技术指标和价格走势时向回搜索的时间范围（自然日）。"
    )
    if selected_lookback_days != saved_lookback:
        update_pref("lookback_days", selected_lookback_days)
    
    # 【新增】新闻/情绪回溯天数选择
    saved_news_lookback = st.session_state.ui_prefs.get("news_lookback_days", 7)
    selected_news_lookback_days = st.slider(
        "新闻/情绪分析窗口 (天):", 
        min_value=1, 
        max_value=30, 
        value=saved_news_lookback,
        help="设定 AI 分析新闻和社交媒体情绪时向回搜索的时间范围（自然日）。"
    )
    if selected_news_lookback_days != saved_news_lookback:
        update_pref("news_lookback_days", selected_news_lookback_days)
    
    # 存储位置 / LLM 提供商 / API Key / 模型 已迁移至顶部 "⚙️ 配置" tab
    st.markdown("---")
    position_status_option = st.radio("您当前是否持有该股票？", options=["否，我没有持仓", "是，我已持有仓位"], index=0, horizontal=True)
    has_position = "已持有" if "是" in position_status_option else "未持有"
    st.markdown("---")
    
    # 【修改】“开始分析”前进行前置校验
    if st.button("🚀 开始分析", use_container_width=True):
        # 获取当前提供商对应的环境变量名
        target_env_var = env_key_map.get(selected_llm_provider_name.lower())
        # 校验：输入框有填 OR 环境变量里有
        has_key = bool(input_api_key) or (target_env_var and os.environ.get(target_env_var))
        
        if not selected_ticker:
            st.error("请输入股票代码（Ticker），例如 NVDA")
        elif not has_key:
            st.error(f"❌ 缺少 API Key！请在左侧填入 {selected_llm_provider_name} 的 Key，或点击下方按钮保存到本地。")
            st.info("💡 提示：您可以点击侧边栏的『保存到 .env』按钮，这样下次启动就不用再填了。")
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
            st.sidebar.error("请至少选择一位分析师。")
            st.session_state.start_analysis = False
        elif not shallow_thinker or not deep_thinker: 
            st.sidebar.error("请为选择的提供商选择模型。")
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
            try:
                for chunk in graph.graph.stream(init_agent_state, **args):
                    final_chunk_for_state = chunk
                    progress_value = 0; progress_text = "分析已开始..."
                    if chunk.get("final_trade_decision"): progress_value = 100; progress_text = "阶段 5/5: 已生成最终决策"
                    elif chunk.get("risk_debate_state") and chunk["risk_debate_state"]["history"]: progress_value = 85; progress_text = "阶段 4/5: 风险管理团队辩论中..."
                    elif chunk.get("trader_investment_plan"): progress_value = 70; progress_text = "阶段 3/5: 交易团队制定计划中..."
                    elif chunk.get("investment_plan"): progress_value = 50; progress_text = "阶段 2/5: 研究经理决策中..."
                    elif chunk.get("investment_debate_state") and chunk["investment_debate_state"]["history"]: progress_value = 35; progress_text = "阶段 2/5: 研究团队辩论中..."
                    elif any(chunk.get(f"{a.value}_report") for a in selected_analysts): progress_value = 15; progress_text = "阶段 1/5: 分析师团队收集中..."
                    progress_placeholder.progress(progress_value, text=progress_text)

                    # 为下方的调试监控器预留一个循环内可更新的占位符（仅首次进入时有效）
                    if 'live_debug_placeholder' not in locals():
                        st.markdown("---")
                        live_debug_placeholder = st.empty()

                    # 【并发补单】当流中出现 report 时，代表对应分析师已跑完并发 SubGraph
                    if chunk.get("market_report"): st.session_state.agent_status["市场分析师"] = "completed"
                    if chunk.get("news_report"): st.session_state.agent_status["新闻分析师"] = "completed"
                    if chunk.get("sentiment_report"): st.session_state.agent_status["舆情分析师"] = "completed"
                    if chunk.get("fundamentals_report"): st.session_state.agent_status["基本面分析师"] = "completed"

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
                st.error(f"❌ 分析出错: {str(e)}")
                with st.expander("🔍 错误详细追踪"):
                    import traceback
                    st.code(traceback.format_exc())
                st.warning("⚠️ 提示: 如果这是连接错误，请检查网络；如果是 ValueError，可能是指标名称不合法（现已修复体积/指标大部分兼容性问题）。")
                st.session_state.start_analysis = False
                st.session_state.final_state = final_chunk_for_state
                if st.session_state.previous_sender: 
                    st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                st.button("分析已中断，点击重试", on_click=reset_state)

    # 2. 分析完成后的视图 (新分析 或 加载的历史)
    elif st.session_state.final_state:
        final_state = st.session_state.final_state

        # 从 final_state 中获取元数据
        ticker_from_state = final_state.get('company_of_interest', 'N/A')
        date_from_state = final_state.get('trade_date', 'N/A')

        st.success(f"✅ 分析完成: **{ticker_from_state}** ({date_from_state})")
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

    # 3. 初始欢迎屏幕
    else:
        st.info("请在左侧侧边栏配置您的分析参数，然后点击 **“开始分析”**。")


# ---- 📚 历史分析 ----
with tab_history:
    st.subheader("📚 历史分析记录")
    st.caption(f"当前存储目录：`{RESULTS_DIR}`")
    historical_analyses = load_historical_analyses(RESULTS_DIR)

    if not historical_analyses:
        st.info("📭 暂无历史记录。完成一次新分析后会自动出现在这里。")
    else:
        # 顶部统计行
        _total_runs = sum(len(r) for r in historical_analyses.values())
        st.markdown(
            f"📊 共 **{len(historical_analyses)}** 只标的 · "
            f"**{_total_runs}** 次历史分析"
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

        if not _sorted_tickers:
            st.warning(f"未找到匹配 '{_filter}' 的记录。")
        else:
            # 三列卡片网格，便于快速扫视
            _cols_per_row = 3
            _ticker_rows = [
                _sorted_tickers[i:i + _cols_per_row]
                for i in range(0, len(_sorted_tickers), _cols_per_row)
            ]
            for _row in _ticker_rows:
                _cols = st.columns(_cols_per_row)
                for _col, _ticker in zip(_cols, _row):
                    _runs = historical_analyses[_ticker]
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
    st.header("🏥 系统健康检查")
    st.caption("检测各项依赖是否就绪。建议每次启动后看一眼，避免分析跑到一半才发现缺组件。")

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

    # 2) OpenCLI 是否在 PATH（雪球 / Reddit / 新浪 都依赖它）
    import shutil as _shutil
    _opencli_path = _shutil.which("opencli")
    _diag_results.append({
        "name": "OpenCLI 浏览器桥",
        "ok": bool(_opencli_path),
        "detail": f"已安装：`{_opencli_path}`" if _opencli_path
                  else "❌ 未找到 `opencli` 命令",
        "fix": "运行 `npm install -g @jackwener/opencli` 并安装 Chrome 扩展" if not _opencli_path else None,
    })

    # 3) akshare 是否可 import（A 股数据源）
    _ak_ok = False
    _ak_version = "?"
    try:
        import akshare as _ak  # noqa
        _ak_ok = True
        _ak_version = getattr(_ak, "__version__", "?")
    except ImportError as _exc:
        _ak_exc = str(_exc)
    _diag_results.append({
        "name": "akshare 数据库",
        "ok": _ak_ok,
        "detail": f"已安装 v{_ak_version}" if _ak_ok else f"❌ 未安装",
        "fix": "运行 `pip install akshare`" if not _ak_ok else None,
    })

    # 4) Playwright Chromium（PDF 导出依赖）
    _pw_ok = False
    try:
        from playwright.sync_api import sync_playwright as _spw  # noqa
        # 不实际启动 browser（耗时），只检查 import
        _pw_ok = True
    except Exception as _exc:
        _pw_exc = str(_exc)
    _diag_results.append({
        "name": "Playwright (PDF 导出)",
        "ok": _pw_ok,
        "detail": "已安装" if _pw_ok else f"❌ 未安装：{_pw_exc[:80]}",
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