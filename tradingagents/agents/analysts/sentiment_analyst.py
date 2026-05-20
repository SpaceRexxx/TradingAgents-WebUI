"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches three complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  1. News headlines     — Yahoo Finance (institutional framing)
  2. StockTwits messages — retail-trader posts indexed by cashtag, with
                           user-labeled Bullish/Bearish sentiment tags
  3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. The LLM produces the sentiment report in a single invocation.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_methodology,
    get_news,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.eastmoney_sentiment import (
    fetch_eastmoney_sentiment,
    to_a_share_code,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.xueqiu import fetch_xueqiu_comments

_REDDIT_DISABLED_PLACEHOLDER = (
    "<Reddit 数据源已在配置中关闭（reddit_enabled=False）。"
    "Reddit WAF 要求 JS 挑战，普通 HTTP 客户端无法通过；如需启用请配置 PRAW OAuth。>"
)


def _days_back(trade_date: str, days: int = 7) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data, injects them into the
    prompt as structured blocks, and produces a sentiment report in a
    single LLM call.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        lookback = state.get("news_lookback_days", 7)
        start_date = _days_back(end_date, lookback)
        instrument_context = build_instrument_context(ticker)

        # Pre-fetch sources. Each fetcher degrades gracefully and returns a
        # string (no exceptions surface from here), so the LLM always sees
        # something — either real data or a clear placeholder.
        # Routing: A-share tickers get China-specific sources; US/HK keep
        # the original StockTwits + Reddit pair.
        news_block = get_news.func(ticker, start_date, end_date)
        is_a_share = to_a_share_code(ticker) is not None

        if is_a_share:
            # StockTwits doesn't cover A-shares -> Eastmoney 千股千评.
            # Reddit has near-zero China-stock discussion -> Xueqiu.
            quant_block = fetch_eastmoney_sentiment(ticker)
            community_block = fetch_xueqiu_comments(ticker, limit=15)
        else:
            quant_block = fetch_stocktwits_messages(ticker, limit=30)
            if get_config().get("reddit_enabled", False):
                community_block = fetch_reddit_posts(ticker)
            else:
                community_block = _REDDIT_DISABLED_PLACEHOLDER

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            quant_block=quant_block,
            community_block=community_block,
            is_a_share=is_a_share,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一名负责协作的 AI 助手，与其他分析师一起工作。"
                    "如果你或其他助手已得出 FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** 或最终交付物，"
                    "请在回复开头加上 FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** 以便团队知道停止。"
                    "\n{system_message}\n"
                    "供你参考，当前日期为 {current_date}。{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # No bind_tools — the data is already in the prompt; a single LLM
        # call produces the report directly.
        chain = prompt | llm
        result = chain.invoke(state["messages"])

        if not (result.content or "").strip():
            import logging
            logging.getLogger(__name__).warning(
                "Sentiment Analyst: returned empty content; retrying once"
            )
            result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    quant_block: str,
    community_block: str,
    is_a_share: bool,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks.

    The data sources differ for A-share vs US/HK tickers, so the
    quantitative-sentiment block and community-discussion block carry
    different platform descriptions and analysis guidance.
    """
    lookback_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days

    if is_a_share:
        quant_section_title = "东方财富千股千评 —— A 股结构化情绪指标"
        quant_section_desc = (
            "聚合了综合得分、关注指数、机构参与度、主力成本和近期参与意愿变化等量化指标。"
            "综合得分越高（>70 偏强）反映东方财富的多空综合判断越乐观；关注指数反映散户关注度（0–100）；"
            "机构参与度反映主力资金的活跃度（A 股独有信号）。"
        )
        community_section_title = "雪球讨论流 —— A 股中长线投资者社区"
        community_section_desc = (
            "雪球是中国最大的严肃投资者社区（类似国外的 Reddit r/investing + r/stocks），用户多为基金经理、行业分析师和长期投资者。"
            "每条帖子带有点赞数、评论数和转发数，可用作互动度加权。"
        )
        quant_analysis_tip = (
            "**将东方财富综合得分和关注度趋势作为量化情绪锚点。** "
            "综合得分 ≥70 为乐观；50–70 中性偏强；30–50 中性偏弱；<30 偏弱。"
            "关注指数上升 + 综合得分上升 = 散户跟风加仓信号；关注指数高但得分下降 = 可能是接盘风险。"
        )
        community_analysis_tip = (
            "**雪球讨论按互动度加权。** 数百赞或评论的帖子代表市场共识方向；零互动的帖子仅作背景。"
            "重点关注帖子内容的语义：投资者是在讨论催化剂、估值、技术形态，还是单纯情绪化追涨杀跌。"
        )
    else:
        quant_section_title = "StockTwits 消息 —— 按 cashtag 索引的散户交易者社交平台"
        quant_section_desc = (
            "节奏较快的信号源。每条消息都附带用户自标的情绪标签（Bullish 看多 / Bearish 看空 / 无标签）以及消息正文。"
        )
        community_section_title = "Reddit 帖子 —— r/wallstreetbets、r/stocks、r/investing（近期）"
        community_section_desc = (
            "社区讨论。通过点赞数和评论数反映关注度。子版风格各异（r/wallstreetbets 常带逆向 / 狂热色彩；"
            "r/stocks 较为理性；r/investing 偏长期视角）。"
        )
        quant_analysis_tip = (
            "**将 StockTwits 看多 / 看空比作为散户情绪的领先信号。** "
            "70/30 的多空比属于温和看多；≥90/10 可能预示过度延伸和反向风险；50/50 表示不确定。"
            "样本量很重要 —— 应基于实际消息数而不是单纯百分比。"
        )
        community_analysis_tip = (
            "**按互动度加权 Reddit 帖子。** 400 赞 / 200 评论的帖子反映社区关注度；3 赞的帖子只是噪音。"
            "阅读正文摘要以获取上下文 —— 仅看标题常常误导。"
        )

    _base = f"""你是一名金融市场情绪分析师。你的任务是为 {ticker} 在 {start_date} 至 {end_date} 期间，基于以下三个已经预先采集好的互补数据源，撰写一份全面的情绪分析报告。

## 数据源（已预先获取，包含在本提示中）

### 新闻头条 —— Yahoo Finance，最近 {lookback_days} 天
机构视角，事实驱动，节奏较慢的信号源。

<start_of_news>
{news_block}
<end_of_news>

### {quant_section_title}
{quant_section_desc}

<start_of_quant_sentiment>
{quant_block}
<end_of_quant_sentiment>

### {community_section_title}
{community_section_desc}

<start_of_community>
{community_block}
<end_of_community>

## 分析方法（最佳实践）

1. {quant_analysis_tip}

2. **关注跨数据源的背离。** 若新闻基调偏空而量化情绪压倒性看多，这种错配本身就是信号 —— 可能意味着散户押注于新闻流尚未追上的逻辑（反之亦然，散户在追涨而机构持谨慎态度）。

3. {community_analysis_tip}

4. **区分观点与事件。** 新闻标题（"宣布与某公司达成战略合作"）是事件；社区帖子（"全仓买入，要起飞了"）是观点。两者都是输入，但在结论中权重应不同。

5. **识别反复出现的叙事主题。** 哪个话题在各数据源中反复出现？那就是当前情绪的主导叙事。

6. **诚实面对数据局限。** 若量化情绪数据样本不足，或某个数据源返回 "<...>" 占位符，情绪解读的可靠性下降 —— 应在报告中明确标注此局限。

7. **识别催化剂与风险**，这些会在各数据源中浮现 —— 即将公布的财报、新品发布、竞争威胁、宏观消息等。

8. **过往情绪不具备预测性。** 应将你的结论定位为给交易员的信号，与基本面和技术面一同权衡，而非价格预测。

9. **拒绝骑墙。** 不要仅仅陈述"趋势好坏参半"或"信号矛盾"就结束分析。即使数据混合，也要提供详细、精细、可操作的洞察，让交易者和投资者能基于你的分析做出决策。

## 输出要求

撰写一份**排版精美、信息密度高**的情绪报告，按以下顺序：

1. **总体情绪方向** —— 看多（Bullish）/ 看空（Bearish）/ 中性（Neutral）/ 混合（Mixed），并基于数据质量和样本量给出简要的置信度说明。
2. **分数据源分解** —— 新闻 / 量化情绪 / 社区讨论 各自给出了什么信号，附具体证据。
3. **跨数据源的背离、共识和关键叙事**。
4. **数据揭示的催化剂与风险**。
5. **对交易者和投资者的实操影响** —— 把你的发现转化为具体的操作启示（例如：何种情绪组合适合加仓 / 减仓 / 观望，需要监控哪些后续信号）。
6. **报告末尾附 Markdown 表格**，汇总关键情绪信号、方向、来源和支撑证据。

**重要指令：你的所有标题、章节名称、字段名和正文必须全部使用中文撰写。禁止使用任何英文章节标题（如 "Overall Sentiment Direction"、"Source-by-Source Breakdown" 等）。**{get_language_instruction()}"""
    return _base + "\n\n---\n以下是必须遵循的分析方法论:\n" + get_methodology("sentiment")


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
