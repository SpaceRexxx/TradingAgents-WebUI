# webapp.py (v2 - 包含持久化历史记录功能)
# 功能:
# - 【新】分析完成后自动保存结果 (JSON + PDF) 到 results/ 目录
# - 【新】侧边栏增加 "历史分析记录" 浏览器
# - 【新】支持点击加载历史记录，并立即下载对应的 PDF
# - 使用 Playwright 生成高质量 PDF 报告
# - 实时更新代理状态和进度

import streamlit as st
import datetime
from pathlib import Path
import re
import io
import asyncio
import os  # 【新增】
import json  # 【新增】

# 自动加载 .env 文件（兼容未激活 conda 环境的情况）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass

# 导入PDF生成库
import markdown2
from playwright.async_api import async_playwright

# 导入项目核心组件
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType

# --- 页面基础配置 ---
st.set_page_config(layout="wide", page_title="TradingAgents Web")
st.title("📈 TradingAgents: 智能交易分析框架")

# --- 定义团队结构 ---
TEAMS_STRUCTURE = {
    "分析师团队": ["市场分析师", "社交媒体分析师", "新闻分析师", "基本面分析师"],
    "研究团队": ["多头研究员", "空头研究员", "研究经理"],
    "交易团队": ["交易员"],
    "风险管理团队": ["激进型分析师", "保守型分析师", "中立型分析师", "投资组合经理"],
}
SENDER_MAP = {
    "Market Analyst": "市场分析师", "News Analyst": "新闻分析师",
    "Social Analyst": "社交媒体分析师", "Fundamentals Analyst": "基本面分析师",
    "Bull Researcher": "多头研究员", "Bear Researcher": "空头研究员",
    "Research Manager": "研究经理", "Trader": "交易员",
    "Risky Analyst": "激进型分析师", "Safe Analyst": "保守型分析师",
    "Neutral Analyst": "中立型分析师", "Risk Judge": "投资组合经理"
}
# 【新增】结果保存目录
RESULTS_DIR = Path(DEFAULT_CONFIG.get("results_dir", "./results"))

# --- 初始化 Session State ---
if 'agent_status' not in st.session_state: st.session_state.agent_status = {}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'final_state' not in st.session_state: st.session_state.final_state = None
if 'previous_sender' not in st.session_state: st.session_state.previous_sender = None
if 'show_live_report_view' not in st.session_state: st.session_state.show_live_report_view = False
if 'start_analysis' not in st.session_state: st.session_state.start_analysis = False # 【修改】确保存在
if 'current_analysis_paths' not in st.session_state: st.session_state.current_analysis_paths = None # 【新增】


# --- Helper 函数 ---
def reset_state():
    """重置整个应用的会话状态，用于开始新的分析"""
    status_dict = {agent: "pending" for team in TEAMS_STRUCTURE.values() for agent in team}
    st.session_state.agent_status = status_dict
    st.session_state.messages = []
    st.session_state.final_state = None
    st.session_state.previous_sender = None
    st.session_state.show_live_report_view = False
    st.session_state.start_analysis = False # 【新增】
    st.session_state.current_analysis_paths = None # 【新增】

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

# ----- PDF 生成方案 (Playwright) -----
async def _async_generate_pdf_with_playwright(styled_html):
    async with async_playwright() as p:
        browser = await p.chromium.launch(); page = await browser.new_page()
        # 注意：这里我们使用 set_content，但如果您的 CSS 依赖外部字体（如 NotoSansSC），
        # 您可能需要将字体文件托管在某个地方，或者使用 base64 嵌入到 CSS 中。
        # 为了简单起见，我们假设 Playwright 可以访问本地字体或回退到系统字体。
        # 一个更健壮的方法是确保 CSS 是完全自包含的。
        await page.set_content(styled_html, wait_until='networkidle') 
        pdf_bytes = await page.pdf(format='A4', margin={'top': '1.5cm', 'bottom': '1.5cm', 'left': '1.5cm', 'right': '1.5cm'})
        await browser.close(); return pdf_bytes

def generate_pdf_report(final_state, ticker, analysis_date):
    """(修改) 此函数现在只负责生成 PDF 的字节流，不再与 UI 交互"""
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
        # 【修改】使用更通用的字体族以提高 PDF 兼容性，避免依赖本地文件
        css = """body { font-family: sans-serif; font-size: 10pt; line-height: 1.6; } h1 { font-size: 22pt; color: #1E293B; text-align: center; } h2 { font-size: 16pt; color: #334155; border-bottom: 2px solid #f1f5f9; padding-bottom: 6px; margin-top: 25px;} h3 { font-size: 13pt; color: #475569; margin-top: 20px;} table { border-collapse: collapse; width: 100%; margin-top: 15px; } th, td { border: 1px solid #e2e8f0; text-align: left; padding: 8px; } th { background-color: #f8fafc; font-weight: bold; }"""
        styled_html = f"<html><head><meta charset='UTF-8'><style>{css}</style></head><body>{html_body}</body></html>"
        
        # 运行异步的 Playwright
        pdf_data = asyncio.run(_async_generate_pdf_with_playwright(styled_html))
        return pdf_data
    except Exception as e:
        st.error(f"使用 Playwright 生成PDF时发生意外错误: {e}"); import traceback; traceback.print_exc(); return None

# --- UI 组件 (侧边栏) ---
with st.sidebar:
    st.header("分析配置")
    selected_ticker = st.text_input("请输入股票代码:", value="").upper()
    analysis_date = st.date_input("请选择分析日期:", datetime.date.today(), max_value=datetime.date.today()).strftime("%Y-%m-%d")
    analyst_options = {"市场分析师": AnalystType.MARKET, "社交媒体分析师": AnalystType.SOCIAL, "新闻分析师": AnalystType.NEWS, "基本面分析师": AnalystType.FUNDAMENTALS}
    selected_analyst_names = st.multiselect("请选择分析师团队:", options=list(analyst_options.keys()), default=list(analyst_options.keys()))
    selected_analysts = [analyst_options[name] for name in selected_analyst_names]
    depth_options = {"浅层 - 少量辩论": 1, "中等 - 中等辩论": 3, "深入 - 深度辩论": 5}
    selected_depth_name = st.selectbox("请选择研究深度:", options=list(depth_options.keys()), index=2)
    selected_research_depth = depth_options[selected_depth_name]
    provider_options = {"DeepSeek": "https://api.deepseek.com/v1", "OpenAI": "https://api.openai.com/v1", "Google": "https://generativelen/v1"}
    selected_llm_provider_name = st.selectbox("请选择 LLM 提供商:", options=list(provider_options.keys()))
    backend_url = provider_options[selected_llm_provider_name]
    st.markdown("---")
    st.subheader("选择模型引擎")
    SHALLOW_AGENT_OPTIONS = { "deepseek": [("DeepSeek-通用", "deepseek-chat"), ("DeepSeek-深度思考", "deepseek-reasoner")], "openai": [("GPT-4o mini - 快速高效", "gpt-4o-mini"), ("GPT-4o - 标准模型", "gpt-4o")], "google": [("Gemini 1.5 Flash - 高性价比", "gemini-1.5-flash-latest")] }
    DEEP_AGENT_OPTIONS = { "deepseek": [("DeepSeek-通用", "deepseek-chat"), ("DeepSeek-深度思考", "deepseek-reasoner")], "openai": [("GPT-4o - 旗舰模型", "gpt-4o"), ("GPT-4 Turbo - 高性能", "gpt-4-turbo")], "google": [("Gemini 1.5 Pro - 先进推理", "gemini-1.5-pro-latest")]}
    provider_key = selected_llm_provider_name.lower()
    shallow_options = SHALLOW_AGENT_OPTIONS.get(provider_key, [])
    deep_options = DEEP_AGENT_OPTIONS.get(provider_key, [])
    format_func = lambda x: x[0]
    selected_shallow_tuple = st.selectbox("快速思考引擎:", options=shallow_options, format_func=format_func, help="用于快速、常规任务的轻量级模型")
    shallow_thinker = selected_shallow_tuple[1] if selected_shallow_tuple else None
    selected_deep_tuple = st.selectbox("深度思考引擎:", options=deep_options, format_func=format_func, help="用于复杂分析和深度辩论的强大模型")
    deep_thinker = selected_deep_tuple[1] if selected_deep_tuple else None
    st.markdown("---")
    position_status_option = st.radio("您当前是否持有该股票？", options=["否，我没有持仓", "是，我已持有仓位"], index=0, horizontal=True)
    has_position = "已持有" if "是" in position_status_option else "未持有"
    st.markdown("---")
    
    # 【修改】“开始分析”按钮现在只设置标志
    if st.button("🚀 开始分析", use_container_width=True):
        reset_state()
        st.session_state.start_analysis = True
        st.session_state.has_position = has_position
        st.rerun() # 立即重跑，进入分析逻辑
        
    st.sidebar.markdown("---")
    st.sidebar.header("下载报告")
    download_placeholder = st.sidebar.empty()
    download_placeholder.info("分析完成后，将在此处提供下载链接。")

    # 【新增】历史记录浏览器
    st.sidebar.markdown("---")
    st.sidebar.header("📊 历史分析记录")
    historical_analyses = load_historical_analyses(RESULTS_DIR)
    if not historical_analyses:
        st.sidebar.info("暂无历史记录。")
    else:
        sorted_tickers = sorted(historical_analyses.keys())
        for ticker in sorted_tickers:
            runs = historical_analyses[ticker]
            with st.sidebar.expander(f"**{ticker}** ({len(runs)} 次记录)"):
                for run in runs:
                    st.button(
                        f"加载: {run['date']}",
                        key=f"load_{ticker}_{run['date']}",
                        on_click=load_selected_analysis,
                        args=(run['json_path'],),
                        use_container_width=True
                    )


# --- 主布局与分析逻辑 ---

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
        # 【修改】将配置(config)的创建移到这里
        config = DEFAULT_CONFIG.copy(); 
        config.update({ 
            "max_debate_rounds": selected_research_depth, 
            "max_risk_discuss_rounds": selected_research_depth, 
            "quick_think_llm": shallow_thinker, 
            "deep_think_llm": deep_thinker, 
            "backend_url": backend_url, 
            "llm_provider": selected_llm_provider_name.lower(), 
            "has_position": st.session_state.get("has_position", "未持有"),
            "results_dir": str(RESULTS_DIR) # 确保 config 中有 results_dir
        })
        
        with st.spinner("正在初始化分析图..."):
            graph = TradingAgentsGraph([a.value for a in selected_analysts], config=config, debug=True)
            init_agent_state = graph.propagator.create_initial_state(selected_ticker, analysis_date)
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
                
                with status_placeholder.container():
                    st.subheader("代理状态")
                    current_sender_name = SENDER_MAP.get(chunk.get("sender"))
                    if current_sender_name and current_sender_name != st.session_state.previous_sender:
                        if st.session_state.previous_sender: st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                        st.session_state.agent_status[current_sender_name] = "in_progress"
                        st.session_state.previous_sender = current_sender_name
                    status_md = "| 团队 | 代理 | 状态 |\n| --- | --- | --- |\n"
                    for team, agents in TEAMS_STRUCTURE.items():
                        team_name_tracker = team
                        for agent in agents:
                            if agent in selected_analyst_names or team != "分析师团队":
                                status = st.session_state.agent_status.get(agent, "pending"); status_icon = "⚪" if status == "pending" else ("⏳" if status == "in_progress" else "✅")
                                status_md += f"| {team_name_tracker} | **{agent}** | {status_icon} {status} |\n"; team_name_tracker = ""
                    st.markdown(status_md)
                    
                with messages_placeholder.container():
                    st.subheader("消息与工具日志");
                    if "messages" in chunk and chunk["messages"]:
                        last_message = chunk["messages"][-1]; content_str = str(last_message.content) if hasattr(last_message, 'content') else ''
                        if content_str: st.session_state.messages.append(f"**思考:** {content_str[:200]}...")
                        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                            for tc in last_message.tool_calls: st.session_state.messages.append(f"**🛠️ 工具调用:** `{tc.get('name', 'N/A')}`")
                    st.markdown("\n\n".join(st.session_state.messages[-10:]))
                    
                with report_placeholder.container():
                    display_live_report(chunk)
        except Exception as e:
            st.error(f"❌ 分析中断 (API 连接错误): {str(e)}")
            st.info("💡 提示: 这通常是由于 API 响应过长、网络环境不稳定或 API Key 额度不足引起的。我已经优化了请求体积，请尝试再次点击“开始分析”。")
            st.session_state.start_analysis = False
            st.stop()
            st.session_state.final_state = final_chunk_for_state
            if st.session_state.previous_sender: 
                st.session_state.agent_status[st.session_state.previous_sender] = "completed"
            
            # 【重要】分析刚结束，st.session_state.start_analysis 标志仍然为 True
            # st.session_state.start_analysis = False # 不要在这里设置 False，留在 "分析完成" 视图中处理
            st.rerun() # 重跑以进入 "分析完成" 视图

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
            
    # 【修改】下载按钮逻辑
    pdf_data = None
    # 检查是否是刚加载的历史记录
    if st.session_state.current_analysis_paths:
        pdf_path = Path(st.session_state.current_analysis_paths['pdf'])
        if pdf_path.exists():
            with st.spinner(f"正在加载已保存的 PDF: {pdf_path.name}..."):
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()
        else:
            download_placeholder.error(f"错误: 未找到已保存的 PDF 文件于 {pdf_path}")
            
    # 检查是否是刚完成的新分析 (由 start_analysis 标志判断)
    elif st.session_state.start_analysis:
        with st.spinner("正在生成并保存 PDF 报告... (这可能需要一点时间)"):
            pdf_data = generate_pdf_report(final_state, ticker_from_state, date_from_state)
            if pdf_data:
                # 【调用保存】
                config_for_saving = DEFAULT_CONFIG.copy()
                config_for_saving.update({"results_dir": str(RESULTS_DIR)})
                save_analysis_results(final_state, ticker_from_state, date_from_state, config_for_saving, pdf_data)
                st.toast("分析结果已保存到磁盘！")
        # 【重要】清除标志，防止重复保存
        st.session_state.start_analysis = False 
            
    # 显示下载按钮
    if pdf_data:
        download_placeholder.download_button(
            label="📄 下载完整PDF报告",
            data=pdf_data,
            file_name=f"TradingAgents_Report_{ticker_from_state}_{date_from_state}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    else:
        # 这是一个捕获逻辑，如果既不是新分析也不是加载的，则不显示按钮
        download_placeholder.info("分析完成后，将在此处提供下载链接。")

# 3. 初始欢迎屏幕
else:
    st.info("请在左侧侧边栏配置您的分析参数，然后点击 **“开始分析”**。")