import pandas as pd
import yfinance as yf
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    # Find date column case-insensitively
    date_col = next((c for c in data.columns if c.lower() == "date"), "Date")
    if date_col in data.columns:
        data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
        data = data.dropna(subset=[date_col])

    data.columns = [c.lower() for c in data.columns]
    price_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "ticker symbol for the company"],
        indicator: Annotated[
            str, "quantitative indicators based off of the stock data for the company"
        ],
        curr_date: Annotated[
            str, "curr date for retrieving stock price data, YYYY-mm-dd"
        ],
    ):
        config = get_config()

        today_date = pd.Timestamp.today()
        curr_date_dt = pd.to_datetime(curr_date)

        end_date = today_date
        start_date = today_date - pd.DateOffset(years=15)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        # Ensure cache directory exists
        os.makedirs(config["data_cache_dir"], exist_ok=True)

        data_file = os.path.join(
            config["data_cache_dir"],
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )

        if os.path.exists(data_file):
            data = pd.read_csv(data_file, on_bad_lines="skip")
        else:
            data = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            data = data.reset_index()
            data.to_csv(data_file, index=False)

        data = _clean_dataframe(data)
        
        # 【关键修复】stockstats 0.6.0+ 解析器对 'date' 列极度敏感
        #  必须将日期设为索引 (Index) 而非普通列，以避免指标解析时的名称冲突
        #  同时也统一了日期格式
        data['date'] = pd.to_datetime(data['date'])
        data.set_index('date', inplace=True)
        
        # 包装为 StockDataFrame
        df = wrap(data)
        
        # 触发指标计算
        try:
            if indicator == 'obv':
                import numpy as np
                df['obv'] = (np.sign(df['close'].diff()).fillna(0) * df['volume']).cumsum()
            else:
                df[indicator]
        except Exception as e:
            # 记录详细错误但返回 N/A，防止分析流程中断
            print(f"Stockstats error for {symbol} {indicator}: {e}")
            return f"N/A: Error calculating {indicator}"

        # 通过索引进行日期匹配
        curr_date_str = curr_date_dt.strftime("%Y-%m-%d")
        
        # 在索引中寻找匹配日期
        # index 是 DatetimeIndex，直接按日期字符串筛选
        try:
            matching_rows = df[df.index.strftime("%Y-%m-%d") == curr_date_str]
            if not matching_rows.empty:
                indicator_value = matching_rows[indicator].values[0]
                return float(indicator_value) if not pd.isna(indicator_value) else "N/A"
            else:
                return "N/A: Not a trading day (weekend or holiday)"
        except Exception:
            return "N/A: Date filtering error"
