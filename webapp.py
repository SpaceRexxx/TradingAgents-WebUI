# webapp.py (最终优化版 - 修复PDF表格和文本溢出)

import streamlit as st
import datetime
from pathlib import Path
import re
import io

# 导入PDF生成库
import markdown2
from xhtml2pdf import pisa

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
    "风险管理团队": ["激进型分析师", "中立型分析师", "保守型分析师", "投资组合经理"],
}
SENDER_MAP = { "Market Analyst": "市场分析师", "News Analyst": "新闻分析师", "Social Analyst": "社交媒体分析师", "Fundamentals Analyst": "基本面分析师", "Bull Researcher": "多头研究员", "Bear Researcher": "空头研究员", "Research Manager": "研究经理", "Trader": "交易员", "Risky Analyst": "激进型分析师", "Safe Analyst": "保守型分析师", "Neutral Analyst": "中立型分析师", "Risk Judge": "投资组合经理" }

# --- 初始化 Session State ---
if 'agent_status' not in st.session_state: st.session_state.agent_status = {}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'final_state' not in st.session_state: st.session_state.final_state = None
if 'previous_sender' not in st.session_state: st.session_state.previous_sender = None

# --- Helper 函数 ---
def reset_state():
    status_dict = {agent: "pending" for team in TEAMS_STRUCTURE.values() for agent in team}
    st.session_state.agent_status = status_dict
    st.session_state.messages = []
    st.session_state.final_state = None
    st.session_state.previous_sender = None

def get_latest_argument(history: str, agent_prefix: str) -> str:
    prefixes = { "Bull Analyst": ["Bull Analyst", "多头分析师"], "Bear Analyst": ["Bear Analyst", "空头分析师"], "Risky Analyst": ["Risky Analyst", "激进型分析师"], "Safe Analyst": ["Safe Analyst", "保守型分析师"], "Neutral Analyst": ["Neutral Analyst", "中立型分析师"], }
    pattern = f"(?:{'|'.join(prefixes.get(agent_prefix, [agent_prefix]))}):(.*?)(?=\n(?:{'|'.join([p for sublist in prefixes.values() for p in sublist])}):|$)"
    matches = re.findall(pattern, history, re.DOTALL)
    return matches[-1].strip() if matches else "等待发言..."

# ----- START: 最终优化的 PDF 生成函数 -----
def generate_pdf_report(final_state, ticker, analysis_date):
    """根据最终分析状态生成PDF报告"""
    try:
        report_parts = [f"<h1>{ticker} 交易分析报告</h1>", f"<p><b>分析日期:</b> {analysis_date}</p><hr>"]
        report_keys_in_order = [ ("第一阶段：分析师团队报告", [ ("market_report", "市场分析报告"), ("news_report", "新闻分析报告"), ("sentiment_report", "社交情绪报告"), ("fundamentals_report", "基本面分析报告"), ]), ("第二阶段：研究团队决策", [("investment_plan", "")]), ("第三阶段：交易团队计划", [("trader_investment_plan", "")]), ("第四/五阶段：风险管理与最终决策", [("final_trade_decision", "")]), ]
        for section_title, keys in report_keys_in_order:
            section_content = []
            for key, sub_title in keys:
                if final_state.get(key) and final_state[key]:
                    content = final_state[key]
                    if sub_title: section_content.append(f"<h3>{sub_title}</h3>{content}")
                    else: section_content.append(content)
            if section_content: report_parts.append(f"<h2>{section_title}</h2>" + "\n".join(section_content))
        
        full_markdown = "\n\n".join(report_parts)
        html = markdown2.markdown(full_markdown, extras=["tables", "fenced-code-blocks", "header-ids", "break-on-newline"])
        
        css = """
        @font-face { font-family: 'NotoSansSC'; src: url('fonts/NotoSansSC-Regular.ttf'); }
        @page { size: a4 portrait; margin: 1.5cm; }
        body { font-family: 'NotoSansSC', sans-serif; font-size: 10pt; line-height: 1.6; }
        h1 { font-size: 22pt; color: #1E293B; text-align: center; }
        h2 { font-size: 16pt; color: #334155; border-bottom: 2px solid #64748B; padding-bottom: 6px; margin-top: 25px;}
        h3 { font-size: 13pt; color: #475569; margin-top: 20px;}
        
        /* 强制所有元素在需要时换行 */
        p, li, th, td, div {
            word-wrap: break-word;
            overflow-wrap: break-word;
        }

        /* 表格样式 */
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #cbd5e1; text-align: left; padding: 8px; }
        th { background-color: #f1f5f9; font-weight: bold; }

        /* 针对“关键指标汇总表”的特定修复 */
        /* 为第一列（指标类别）设置固定宽度和垂直对齐 */
        table td:first-child {
            width: 120px; /* 或根据需要调整 */
            min-width: 120px;
            vertical-align: middle; /* 垂直居中对齐 */
        }
        /* 为第二列（具体指标）设置强制不换行 */
        table td:nth-child(2) {
            white-space: nowrap;
        }
        """
        styled_html = f"<html><head><meta charset='UTF-8'><style>{css}</style></head><body>{html}</body></html>"
        
        pdf_buffer = io.BytesIO()
        pisa.CreatePDF(io.StringIO(styled_html), dest=pdf_buffer, encoding='UTF-8')

        if pisa.pisaDocument.err: st.error(f"生成PDF时出错: {pisa.pisaDocument.err}"); return None
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception as e:
        st.error(f"生成PDF时发生意外错误: {e}"); import traceback; traceback.print_exc(); return None
# ----- END: 最终优化的 PDF 生成函数 -----


# --- UI 组件 (侧边栏) ---
with st.sidebar:
    st.header("分析配置")
    selected_ticker = st.text_input("请输入股票代码:", value="AAPL").upper()
    analysis_date = st.date_input("请选择分析日期:", datetime.date.today(), max_value=datetime.date.today()).strftime("%Y-%m-%d")
    analyst_options = {"市场分析师": AnalystType.MARKET, "社交媒体分析师": AnalystType.SOCIAL, "新闻分析师": AnalystType.NEWS, "基本面分析师": AnalystType.FUNDAMENTALS}
    selected_analyst_names = st.multiselect("请选择分析师团队:", options=list(analyst_options.keys()), default=list(analyst_options.keys()))
    selected_analysts = [analyst_options[name] for name in selected_analyst_names]
    depth_options = {"浅层 - 少量辩论": 1, "中等 - 中等辩论": 3, "深入 - 深度辩论": 5}
    selected_depth_name = st.selectbox("请选择研究深度:", options=list(depth_options.keys()), index=2)
    selected_research_depth = depth_options[selected_depth_name]
    provider_options = {"DeepSeek": "https://api.deepseek.com/v1", "OpenAI": "https://api.openai.com/v1", "Google": "https://generativelanguage.googleapis.com/v1"}
    selected_llm_provider_name = st.selectbox("请选择 LLM 提供商:", options=list(provider_options.keys()))
    backend_url = provider_options[selected_llm_provider_name]
    st.markdown("---")
    st.subheader("选择模型引擎")
    SHALLOW_AGENT_OPTIONS = { "deepseek": [("DeepSeek-通用", "deepseek-chat"), ("DeepSeek-深度思考", "deepseek-reasoner")], "openai": [("GPT-4o mini - 快速高效", "gpt-4o-mini"), ("GPT-4o - 标准模型", "gpt-4o")], "google": [("Gemini 1.5 Flash - 高性价比，自适应", "gemini-1.5-flash-latest")] }
    DEEP_AGENT_OPTIONS = { "deepseek": [("DeepSeek-通用", "deepseek-chat"), ("DeepSeek-深度思考", "deepseek-reasoner")], "openai": [("GPT-4o - 旗舰模型", "gpt-4o"), ("GPT-4 Turbo - 高性能", "gpt-4-turbo")], "google": [("Gemini 1.5 Pro - 先进推理", "gemini-1.5-pro-latest"), ("Gemini 1.5 Flash - 高性价比", "gemini-1.5-flash-latest")] }
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
    if st.button("🚀 开始分析", use_container_width=True, on_click=reset_state):
        st.session_state.start_analysis = True
        st.session_state.has_position = has_position
    st.sidebar.markdown("---")
    st.sidebar.header("下载报告")
    download_placeholder = st.sidebar.empty()
    download_placeholder.info("分析完成后，将在此处提供下载链接。")

# --- 主布局逻辑 ---
if not st.session_state.get('final_state'):
    progress_placeholder = st.empty()
    col1, col2 = st.columns([1, 2])
    with col1: status_placeholder = st.empty(); messages_placeholder = st.empty()
    with col2: report_placeholder = st.empty()

# --- 主分析逻辑 ---
if st.session_state.get('start_analysis', False):
    if not selected_analysts: st.sidebar.error("请至少选择一位分析师。"); st.session_state.start_analysis = False
    elif not shallow_thinker or not deep_thinker: st.sidebar.error("请为选择的提供商选择模型。"); st.session_state.start_analysis = False
    else:
        config = DEFAULT_CONFIG.copy(); config.update({ "max_debate_rounds": selected_research_depth, "max_risk_discuss_rounds": selected_research_depth, "quick_think_llm": shallow_thinker, "deep_think_llm": deep_thinker, "backend_url": backend_url, "llm_provider": selected_llm_provider_name.lower(), "has_position": st.session_state.get("has_position", "未持有") })
        with st.spinner("正在初始化分析图..."):
            graph = TradingAgentsGraph([a.value for a in selected_analysts], config=config, debug=True)
            init_agent_state = graph.propagator.create_initial_state(selected_ticker, analysis_date)
            args = graph.propagator.get_graph_args()

        for chunk in graph.graph.stream(init_agent_state, **args):
            st.session_state.final_state = chunk
            
            progress_value = 0; progress_text = "分析已开始..."
            if chunk.get("final_trade_decision"): progress_value = 100; progress_text = "阶段 5/5: 已生成最终决策"
            elif chunk.get("risk_debate_state") and chunk["risk_debate_state"]["history"]: progress_value = 85; progress_text = "阶段 4/5: 风险管理团队辩论中..."
            elif chunk.get("trader_investment_plan"): progress_value = 70; progress_text = "阶段 3/5: 交易团队制定计划中..."
            elif chunk.get("investment_plan"): progress_value = 50; progress_text = "阶段 2/5: 研究经理决策中..."
            elif chunk.get("investment_debate_state") and chunk["investment_debate_state"]["history"]: progress_value = 35; progress_text = "阶段 2/5: 研究团队辩论中..."
            elif any(chunk.get(f"{a.value}_report") for a in selected_analysts): progress_value = 15; progress_text = "阶段 1/5: 分析师团队收集中..."
            with progress_placeholder.container(): st.progress(progress_value, text=progress_text)

            with status_placeholder.container():
                st.subheader("代理状态")
                sender_map = { "Market Analyst": "市场分析师", "News Analyst": "新闻分析师", "Social Analyst": "社交媒体分析师", "Fundamentals Analyst": "基本面分析师", "Bull Researcher": "多头研究员", "Bear Researcher": "空头研究员", "Research Manager": "研究经理", "Trader": "交易员", "Risky Analyst": "激进型分析师", "Safe Analyst": "保守型分析师", "Neutral Analyst": "中立型分析师", "Risk Judge": "投资组合经理" }
                current_sender_name = sender_map.get(chunk.get("sender"))
                if current_sender_name:
                    if st.session_state.previous_sender and st.session_state.previous_sender != current_sender_name: st.session_state.agent_status[st.session_state.previous_sender] = "completed"
                    st.session_state.agent_status[current_sender_name] = "in_progress"
                    st.session_state.previous_sender = current_sender_name
                
                status_md = "| 团队 | 代理 | 状态 |\n| --- | --- | --- |\n"
                for team, agents in TEAMS_STRUCTURE.items():
                    team_name_tracker = team
                    for agent in agents:
                        if agent in selected_analyst_names or team != "分析师团队":
                            status = st.session_state.agent_status.get(agent, "pending")
                            status_icon = "⚪" if status == "pending" else ("⏳" if status == "in_progress" else "✅")
                            status_md += f"| {team_name_tracker} | **{agent}** | {status_icon} {status} |\n"
                            team_name_tracker = ""
                st.markdown(status_md)
            with messages_placeholder.container():
                st.subheader("消息与工具日志"); 
                if "messages" in chunk and chunk["messages"]:
                    last_message = chunk["messages"][-1]
                    if hasattr(last_message, "content") and last_message.content: st.session_state.messages.append(f"**思考:** {last_message.content[:200]}...")
                    if hasattr(last_message, "tool_calls"):
                        for tc in last_message.tool_calls: st.session_state.messages.append(f"**🛠️ 工具调用:** `{tc['name']}`")
                st.markdown("\n\n".join(st.session_state.messages[-10:]))
            with report_placeholder.container():
                st.subheader("实时报告")
                if "risk_debate_state" in chunk and chunk["risk_debate_state"]["history"]:
                    st.subheader("第四/五阶段：风险管理与最终决策"); risk_state = chunk["risk_debate_state"]; r_col1, r_col2, r_col3 = st.columns(3)
                    with r_col1: st.error("**激进派观点**"); st.markdown(risk_state.get("risky_history", ""))
                    with r_col2: st.info("**中立派观点**"); st.markdown(risk_state.get("neutral_history", ""))
                    with r_col3: st.warning("**保守派观点**"); st.markdown(risk_state.get("safe_history", ""))
                    if risk_state.get("judge_decision"): st.success("**最终决策 (投资组合经理):**"); st.markdown(risk_state["judge_decision"])
                elif "trader_investment_plan" in chunk and chunk["trader_investment_plan"]:
                    st.subheader("第三阶段：交易团队计划"); st.markdown(chunk["trader_investment_plan"])
                elif "investment_debate_state" in chunk and chunk["investment_debate_state"]["history"]:
                    st.subheader("第二阶段：研究团队辩论与决策"); debate_state = chunk["investment_debate_state"]; b_col1, b_col2 = st.columns(2)
                    with b_col1: st.info("**多头观点 (Bull)**"); st.markdown(debate_state.get("bull_history", "等待发言..."))
                    with b_col2: st.warning("**空头观点 (Bear)**"); st.markdown(debate_state.get("bear_history", "等待发言..."))
                    if debate_state.get("judge_decision"): st.success("**决策 (研究经理):**"); st.markdown(debate_state["judge_decision"])
                else:
                    st.subheader("第一阶段：分析师团队报告"); report_keys = [("market_report", "市场分析"), ("news_report", "新闻分析"), ("sentiment_report", "社交情绪分析"), ("fundamentals_report", "基本面分析")]; available_reports = [(key, title) for key, title in report_keys if chunk.get(key)]
                    if available_reports:
                        tab_titles = [title for _, title in available_reports]; tabs = st.tabs(tab_titles)
                        for i, (key, title) in enumerate(available_reports):
                            with tabs[i]: st.markdown(chunk[key])
    
    if st.session_state.previous_sender: st.session_state.agent_status[st.session_state.previous_sender] = "completed"
    
    st.session_state.start_analysis = False
    st.rerun()

if st.session_state.get('final_state'):
    final_state = st.session_state.final_state
    
    st.success("✅ 分析完成！")
    
    st.header("📄 完整分析报告")
    if any(final_state.get(key) for key in ["market_report", "news_report", "sentiment_report", "fundamentals_report"]):
        with st.expander("第一阶段：分析师团队报告", expanded=True):
            if final_state.get("market_report"): st.subheader("市场分析报告"); st.markdown(final_state["market_report"])
            if final_state.get("news_report"): st.subheader("新闻分析报告"); st.markdown(final_state["news_report"])
            if final_state.get("sentiment_report"): st.subheader("社交情绪报告"); st.markdown(final_state["sentiment_report"])
            if final_state.get("fundamentals_report"): st.subheader("基本面分析报告"); st.markdown(final_state["fundamentals_report"])
    if final_state.get("investment_plan"):
        with st.expander("第二阶段：研究团队决策", expanded=True): st.markdown(final_state["investment_plan"])
    if final_state.get("trader_investment_plan"):
        with st.expander("第三阶段：交易团队计划", expanded=True): st.markdown(final_state["trader_investment_plan"])
    if final_state.get("final_trade_decision"):
        with st.expander("第四/五阶段：风险管理与最终决策", expanded=True): st.markdown(final_state["final_trade_decision"])

    pdf_data = generate_pdf_report(final_state, final_state['company_of_interest'], final_state['trade_date'])
    if pdf_data:
        download_placeholder.download_button(
            label="📄 下载完整PDF报告",
            data=pdf_data,
            file_name=f"TradingAgents_Report_{final_state['company_of_interest']}_{final_state['trade_date']}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    else:
        download_placeholder.error("生成PDF失败。")