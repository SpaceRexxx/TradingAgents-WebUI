<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

# 📈 TradingAgents (WebUI 版)

本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 衍生并深度重构。原项目构筑了优秀的 AI 交易员多智能体框架，本项目在此基础上完成了**前后端分离架构升级**、大量底层修复与本土化模型/数据扩展。

> **v2.0 架构**：Streamlit 单体已退役并移除，现为 **FastAPI 后端 + React SPA 前端**，CLI 保持独立可用。

## 🌟 核心增强特性

- **前后端分离架构 (v2.0)**：FastAPI 后端（REST + WebSocket，封装引擎、SQLite 历史索引、持久化、按需 PDF）+ React + TypeScript SPA 前端（Vite、Zustand、React Router）。前端以 WebSocket 流式渲染，不再依赖 Streamlit rerun。
- **原生并行化与沙盒引擎**：彻底修复原版多智能体并行运行时的 `INVALID_CONCURRENT_GRAPH_UPDATE` 内存污染与图谱幻觉冲突，四位分析师真正实现 100% 稳定并发。
- **全方位大模型支持**：DeepSeek V4 (Flash / Pro)、小米 MiMo v2.5 Pro、NVIDIA DeepSeek V3、火山引擎 (Volcengine/Ark)、OpenAI、Anthropic、Google Gemini、Qwen、GLM、MiniMax、OpenRouter、xAI、Azure、Ollama，思考模型 `reasoning_content` round-trip 已就绪。
- **A 股原生数据栈**：A 股标的自动切换本土数据源 —— akshare 千股千评 + 雪球讨论（OpenCLI）替代 StockTwits/Reddit，新浪财经宏观 + 东方财富公告 + 财联社替代 Yahoo Finance；美股/港股保持原方案。
- **分析中心全功能还原**：分析师 Checkbox、研究深度、价格/新闻回溯滑块、日期选择器、持仓开关、实时价格 + 中文名、里程碑进度条 + 实时计时器、竖向 Agent 侧栏（点击预览、状态 ⚪/⏳/✅）、本次分析 Token/成本透明度卡片。
- **历史与可观测**：SQLite 历史索引（评级筛选、备注、A/B 分节对比）、累计 Token/成本统计卡片、一键「重建索引」恢复未入库分析、按需 PDF 研报、数据源诊断页。
- **底层重构**：屏蔽 HTTP/2 降级解决 `openai.APIConnectionError`；重构 `memory.py` 消除全局状态逃逸；原生 `SystemMessage` 注入兼容旧版 `langgraph`；修复 `obv` 等指标别名映射。
- **CLI 深度优化**：显式模块导入、流式 chunk 增量 merge（零内存冗余）、代理状态机修复。

---

## 更新日志 (News)

- [2026-05] **v2.0 架构升级**：Streamlit 退役并删除，迁移为 FastAPI 后端 + React SPA；新增 `./dev.sh` 一键同启前后端、可配置下载目录、历史「重建索引」、按需 PDF、单次/累计 Token 成本透明度。
- [2026-05] **v1.9**：四 Tab 布局（分析中心 / 历史分析 / 配置 / 诊断）、SQLite 历史索引、A/B 对比、PDF 导出、小米 MiMo v2.5 Pro、实时 Token 累计统计。
- [2026-04] DeepSeek 升级至 **V4 Flash / V4 Pro**；A 股数据栈本土化（akshare + 雪球 + 新浪 + 东方财富 + 财联社）。
- [2026-03] 整合无缝原生并行执行引擎及火山引擎 / NVIDIA DeepSeek V3 / OpenAI 支持；上游 **TradingAgents v0.2.1** 覆盖 GPT-5.4、Gemini 3.1、Claude 4.6。

<div align="center">

🚀 [系统架构](#tradingagents-系统架构) | 🧱 [技术架构](#-技术架构-v20) | ⚡ [安装](#安装指南-installation) | ▶️ [运行](#-运行项目-running-the-project) | 🤝 [贡献](#参与贡献) | 📄 [引用](#引用)

</div>

## TradingAgents 系统架构

TradingAgents 是一个模拟现实世界顶级量化交易公司运作动态的多智能体（Multi-Agent）框架。由大语言模型驱动的专业化智能体（基本面分析师、情绪专家、技术分析师、交易员、风险管理团队）协同评估市场并通过动态辩论（Debates）寻找最优策略。

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> 本框架专为学术研究与实验设计。实际交易表现受底层模型能力、温度设定、交易周期、数据质量等非确定性因素影响。[本框架不作为任何财务、投资或交易建议。](https://tauric.ai/disclaimer/)

### 分析师团队 (Analyst Team)
- **基本面分析师**：评估财务报表与关键业绩指标，识别内在价值与危险信号。
- **社交情绪分析师**：分析社交媒体与公众情绪，感知短期市场氛围。
- **新闻分析师**：跟踪全球新闻与宏观指标，解读大事件对市场的影响。
- **技术分析师**：运用 MACD、RSI、OBV 等指标检测走势，预测价格动向。

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 研究员团队 (Researcher Team)
- 由“多头（看涨）”与“空头（看跌）”研究员组成，对分析师报告进行挑剔审视，通过结构化辩论权衡收益与风险。

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 交易员 (Trader Agent)
- 汇总分析师与研究员的报告及辩论记录，生成交易计划提案（切入点、止损点、持仓规模）。

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 风险管理团队与投资组合经理 (Risk Management & Portfolio Manager)
- 风险管理团队（激进 / 保守 / 中立型）持续评估组合层面风险，审查交易策略并上交含风险预警的最终评估。
- **投资组合经理**作为最后一道防线，批准或驳回交易提案。

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 🧱 技术架构 (v2.0)

```
┌──────────────────────────┐        HTTP /api  +  WS /ws        ┌───────────────────────────┐
│  前端  frontend/ (React)  │ ──────────────────────────────────▶ │  后端  backend/ (FastAPI)   │
│  Vite · TS · Zustand     │ ◀────── 流式 chunk / 终态事件 ────── │  封装 tradingagents 引擎     │
│  :5173 (开发，代理到 :8765) │                                     │  :8765  REST + WebSocket    │
└──────────────────────────┘                                     │  SQLite 历史索引 / 持久化    │
                                                                  │  按需 PDF (Playwright)      │
        cli/ (Rich/Typer，独立运行，复用同一引擎与结果目录) ───────▶ └───────────────────────────┘
```

- **后端** `backend/`：FastAPI 应用（`backend.main:app`）。`POST /api/analysis/start` 启动分析，`WS /api/analysis/ws/{run_id}` 流式推送逐节点 chunk 与终态事件；历史、对比、诊断、Provider、配置、报价、统计、按需 PDF 等 REST 端点。引擎结果写入 `results_dir` 并建 SQLite 索引。
- **前端** `frontend/`：React + TypeScript SPA，四个路由 Tab：**分析中心 / 历史分析 / 配置 / 诊断**。`useAnalysisStream` 钩子管理 WebSocket 生命周期；客户端从 chunk 推导各 Agent/阶段状态与进度。
- **CLI** `cli/`：纯终端入口，复用同一引擎与结果目录，未受架构迁移影响。
- 结果与索引默认在 `~/Desktop/Stock`，可在 **配置** Tab 改「下载目录」或用环境变量 `TRADINGAGENTS_RESULTS_DIR`。
- 详细文档见 `docs/backend.md`、`docs/frontend.md`。

## 安装指南 (Installation)

依赖 **Python 3.10+**、**Node.js 18+**（前端构建/开发）、以及 **Playwright Chromium 内核**（PDF 渲染）。

### 🍎 macOS (Apple Silicon / Intel)
```bash
# 1. 环境管理工具（如已安装可跳过）
brew install --cask miniconda
brew install node            # Node.js 18+（前端需要）

# 2. 获取项目
git clone https://github.com/SpaceRexxx/TradingAgents-WebUI.git
cd TradingAgents-WebUI

# 3. Python 环境
conda create -n tradingagents python=3.11 -y
conda activate tradingagents

# 4. 依赖 + 浏览器内核
pip install -r requirements.txt
playwright install chromium

# 5. 前端依赖（也可由 ./dev.sh 首次运行时自动安装）
cd frontend && npm install && cd ..
```

### 🪟 Windows (PowerShell / CMD)
```powershell
# 1. 安装 Miniconda 与 Node.js 18+（https://nodejs.org）
git clone https://github.com/SpaceRexxx/TradingAgents-WebUI.git
cd TradingAgents-WebUI

# 2. Python 环境
conda create -n tradingagents python=3.11 -y
conda activate tradingagents

# 3. 依赖 + 内核 + 前端
pip install -r requirements.txt
playwright install chromium
cd frontend; npm install; cd ..
```

### 🐧 Linux (Ubuntu / Debian)
```bash
git clone https://github.com/SpaceRexxx/TradingAgents-WebUI.git
cd TradingAgents-WebUI

sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip nodejs npm -y
python3.11 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
playwright install-deps
cd frontend && npm install && cd ..

# ⚠️ 无界面服务器若 PDF 中文显示为方块，安装中文字体：
# sudo apt install fonts-noto-cjk -y
```

### 🌐 可选依赖：OpenCLI（A 股 / 社交舆情 / 实时报价桥接）

雪球讨论流、新浪财经宏观、东方财富、Reddit，以及分析中心顶部的**实时价格 + 中文名**均通过 [OpenCLI](https://www.npmjs.com/package/@jackwener/opencli) 调用你本地登录态的浏览器抓取。只分析美股且不需要 Reddit 舆情可跳过；分析 **A 股**强烈建议安装。

```bash
# macOS: brew install node ；其它系统见 https://nodejs.org
npm install -g @jackwener/opencli
opencli xueqiu login         # 雪球（实时报价 + A 股舆情）
opencli reddit login         # Reddit（美股社交情绪）
```

### 🛠️ 常见安装问题 (Troubleshooting)

**1. Conda 协议未接受 (CondaToSNonInteractiveError)**
```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

**2. 环境激活报错 (CondaError: Run 'conda init')**
运行 `conda init zsh`(macOS/Linux) 或 `conda init powershell`(Windows)，**关闭并重开终端**后再 `conda activate tradingagents`；仍失败可 `source ~/.zshrc`。

**3. 点击下载 PDF 报错 / 找不到 Executable**
报错 `Executable doesn't exist at /.../headless_shell` 说明只装了 Python 包没装浏览器内核。在已激活的环境中执行：
```bash
playwright install chromium
```

**4. 历史列表缺少最近分析 / 下载 PDF 报「No indexed analysis」**
说明该次分析的报告未入 SQLite 索引（多为旧版本遗留）。在**历史分析**页点击 **「重建索引」**，会从引擎日志补全报告并重建索引。

### 🔄 如何更新 (How to Update)
```bash
git fetch --all
git reset --hard origin/main      # 注意：丢弃本地代码改动
conda activate tradingagents
pip install -r requirements.txt
playwright install chromium
cd frontend && npm install && cd ..
```

### 必需的 API (Required APIs)

可在 Web UI **配置** Tab 直接注入 API Key（写入 `.env` + 进程环境），也可预先配置环境变量：

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT 系列)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude 系列)
export GOOGLE_API_KEY=...          # Google (Gemini 系列)
export DEEPSEEK_API_KEY=...        # DeepSeek V4 Flash / V4 Pro
export NVIDIA_API_KEY=...          # NVIDIA NIM (DeepSeek V3 等，nvapi- 开头)
export ARK_API_KEY=...             # 火山引擎 (Volcengine)
export MIMO_API_KEY=...            # 小米 MiMo v2.5 Pro
export DASHSCOPE_API_KEY=...       # Qwen 国际版
export DASHSCOPE_CN_API_KEY=...    # Qwen 国内版
export ZHIPU_API_KEY=...           # GLM (Z.AI 国际版)
export ZHIPU_CN_API_KEY=...        # GLM (BigModel 国内版)
export MINIMAX_API_KEY=...         # MiniMax 全球版
export MINIMAX_CN_API_KEY=...      # MiniMax 国内版
export OPENROUTER_API_KEY=...      # OpenRouter (多模型聚合)
export XAI_API_KEY=...             # xAI (Grok 系列)
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage 数据源
```

> [!IMPORTANT]
> **WebUI 密钥持久化**：在 **配置** Tab 输入 Key 会写入 `.env` + 进程环境（永不回显）。
> - **本地环境**：推荐，避免重复输入。
> - **公网/云端环境**：**请谨慎保存**，Key 会落盘到服务器，存在泄露风险。

> **💡 模型填写提示**：使用**火山引擎 (Volcengine)** 时，模型名须填火山控制台创建的 **Endpoint ID**（如 `ep-2026xxxx-xxxx`），而非 "DeepSeek-V3"。

推荐复制 `.env.example` 为 `.env` 并填入密钥：
```bash
cp .env.example .env
```

## 🚀 运行项目 (Running the Project)

确保已激活虚拟环境 (`conda activate tradingagents`)。本项目支持两种互补方式。

### 1. Web UI（推荐）

v2.0 为 **React SPA + FastAPI 后端（两个进程）**。一条命令同时启动、保留热重载、`Ctrl+C` 一并退出：

```bash
./dev.sh
```

首次运行会自动 `npm install`。启动后打开 **http://localhost:5173**（前端，`/api` 与 `/ws` 自动代理到后端 :8765）；后端 OpenAPI 文档在 **http://localhost:8765/docs**。可用环境变量 `BACKEND_PORT` 覆盖后端端口。

需要分别启动（调试单侧）时：

```bash
# 终端 1（后端，项目根目录）
uvicorn backend.main:app --port 8765
# 终端 2（前端）
cd frontend && npm install && npm run dev
```

四个 Tab：

- **分析中心**：填股票代码（失焦显示实时价 + 中文名）、日期、持仓开关、分析师 Checkbox、研究深度、价格/新闻回溯滑块 → 开始分析。里程碑进度条 + 实时计时器、左侧 12 个 Agent 状态侧栏（点击预览流式内容）、完成后「本次分析透明度」卡片（输入/输出/总 Token、估算成本、工具调用、数据新鲜度）。
- **历史分析**：顶部「累计统计（所有分析）」卡片；列表支持按 ticker 过滤、备注/评分、A/B 分节 diff、按行下载 PDF、**重建索引**。
- **配置**：注入各 Provider API Key、测试连通性、设置**下载目录**。
- **诊断**：数据源健康探测。

<p align="center">
  <img src="assets/webui_demo.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

> 🎉 **PDF 研报（按需生成）**：分析完成后点击「下载本次 PDF」，后端调起 `Playwright` 将 Markdown 报表实时渲染为 **PDF** 返回（不落盘）。历史页同样支持按行下载；某次未入索引时点「重建索引」恢复。

### 2. CLI 文本端

纯终端环境下，CLI 提供完全并行的分析引擎与 Rich 控制台渲染：

```bash
python -m cli.main
```

- **⚡ 并发分析**：选中的分析师团队真正并行运行，实时进度追踪。
- **🛰️ 供应商全兼容**：DeepSeek、OpenAI、Anthropic、Google、Qwen、GLM、MiniMax、OpenRouter、xAI、火山引擎、NVIDIA、Azure、Ollama。
- **🔐 动态 Key 注入**：启动时检测 Key 状态，缺失时交互式填入并持久化到 `.env`。
- **📄 报告自动保存**：分析结束后保存各阶段报告至 `<results_dir>/<ticker>/<date>/`。

<p align="center">
  <img src="assets/cli_demo.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 🐳 Docker

`docker-compose.yml` 已迁移为后端 + 可选前端服务：

```bash
docker compose up webapp            # 仅后端 (uvicorn :8765)
docker compose up webapp frontend   # 后端 + 前端 dev (:5173)
```

---

## ⚖️ License & Acknowledgements (版权与致谢)

原始框架灵感与基础架构来源于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)，向原作者致以诚挚感谢。本项目沿用 [Apache License 2.0](./LICENSE)。
- Original Work: Copyright 2024-2025 TauricResearch
- Modifications: Copyright 2026 SpaceRexxx

## 参与贡献

欢迎社区贡献！修复 Bug、改进文档、提议新功能均欢迎。后端测试 `pytest tests/backend -v`，前端测试 `cd frontend && npm test`。

## 引用

如果 *TradingAgents* 的框架理念对您的研究有帮助，请引用原作者论文：

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
