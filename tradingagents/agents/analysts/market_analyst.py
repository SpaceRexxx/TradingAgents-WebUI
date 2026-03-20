from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_stock_data,
            get_indicators,
        ]

        # ----- START: 中文翻译和指令修改 -----
        system_message = (
            """你是一名负责分析金融市场的交易助手。你的任务是从以下列表中为给定的市场状况或交易策略选择**最相关的指标**。目标是选择最多**4个**能够提供互补性见解且不冗余的指标。指标类别及各类别下的指标如下：

移动平均线 (Moving Averages):
- close_50_sma: 50日简单移动平均线 (50 SMA): 一个中期趋势指标。用途：识别趋势方向并作为动态支撑/阻力位。提示：该指标滞后于价格；请与更快的指标结合使用以获得及时的信号。
- close_200_sma: 200日简单移动平均线 (200 SMA): 一个长期趋势基准。用途：确认整体市场趋势并识别“黄金交叉”/“死亡交叉”形态。提示：该指标反应缓慢；最适合用于战略性趋势确认，而非频繁的交易入场。
- close_10_ema: 10日指数移动平均线 (10 EMA): 一条反应灵敏的短期平均线。用途：捕捉动量的快速变化和潜在的入场点。提示：在震荡市场中容易产生噪音；请与较长期的平均线一同使用以过滤错误信号。

MACD 相关指标:
- macd: MACD指标: 通过计算EMA的差值来衡量动量。用途：寻找交叉和背离作为趋势变化的信号。提示：在低波动性或横盘市场中，需与其他指标一同确认。
- macds: MACD信号线 (MACD Signal): MACD线的EMA平滑线。用途：使用其与MACD线的交叉来触发交易。提示：应作为更广泛策略的一部分，以避免假阳性信号。
- macdh: MACD柱状图 (MACD Histogram): 显示MACD线与其信号线之间的差距。用途：可视化动量强度并及早发现背离。提示：该指标可能波动较大；在快速变化的市场中需辅以其他过滤器。

动量指标 (Momentum Indicators):
- rsi: 相对强弱指数 (RSI): 衡量动量以标记超买/超卖状况。用途：应用70/30阈值并观察背离以发出反转信号。提示：在强劲趋势中，RSI可能保持在极端水平；务必与趋势分析交叉验证。

波动性指标 (Volatility Indicators):
- boll: 布林带中轨 (Bollinger Middle): 作为布林带基础的20日SMA。用途：作为价格波动的动态基准。提示：请与上下轨结合使用，以有效发现突破或反转。
- boll_ub: 布林带上轨 (Bollinger Upper Band): 通常是中轨线上方2个标准差。用途：发出潜在的超买状况和突破区域信号。提示：需用其他工具确认信号；在强劲趋势中，价格可能会沿着上轨运行。
- boll_lb: 布林带下轨 (Bollinger Lower Band): 通常是中轨线下方2个标准差。用途：指示潜在的超卖状况。提示：需使用额外分析以避免错误的反转信号。
- atr: 平均真实波幅 (ATR): 通过平均真实波幅来衡量波动性。用途：根据当前市场波动性设置止损位和调整头寸大小。提示：这是一个反应性指标，应作为更广泛风险管理策略的一部分。

成交量相关指标 (Volume-Based Indicators):
- vwma: 成交量加权移动平均线 (VWMA): 按成交量加权的移动平均线。用途：通过整合价格行为和成交量数据来确认趋势。提示：注意成交量激增可能导致的扭曲结果；请与其他成交量分析结合使用。

- 请选择能提供多样化和互补信息的指标。避免冗余（例如，不要同时选择 rsi 和 stochrsi）。并简要解释为什么它们适合给定的市场环境。
- 当你调用工具时，请务必使用上面提供的确切指标名称，因为它们是已定义的参数，否则你的调用将会失败。
- 请确保首先调用 get_stock_data 来获取生成指标所需的CSV数据，然后再使用 get_indicators 并附上具体的指标名称。
- 请撰写一份关于你观察到的趋势的非常详尽和细致入微的报告。不要仅仅陈述趋势是混合的，而要提供可能有助于交易者做出决策的详细、精细的分析和见解。
- 确保在报告末尾附加一个Markdown表格，以有组织、易于阅读的方式整理报告中的关键点。
- **重要指令：你的所有分析和最终报告都必须使用中文撰写。**"""
        )
        # ----- END OF MODIFICATION -----

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的人工智能助手，与其他助手协同工作。"
                    "请使用提供的工具来逐步回答问题。"
                    "如果你无法完全回答，没关系；另一位拥有不同工具的助手会接替你未完成的部分。尽你所能去取得进展。"
                    "如果你或任何其他助手得出了最终的交易建议（例如：最终交易建议：**买入/持有/卖出**），请在你的回复前加上“最终交易建议：**买入/持有/卖出**”，以便团队知晓可以停止工作。"
                    "你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是 {current_date}。我们关注的公司是 {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
            "sender": "Market Analyst",
        }

    return market_analyst_node