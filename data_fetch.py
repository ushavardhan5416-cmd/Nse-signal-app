"""
Fetches OHLCV data for NSE symbols.

This starter uses yfinance (free, delayed data, fine for prototyping and
learning). For real-time/production use, swap this module out for a broker
API such as Zerodha Kite Connect, Upstox, or Angel One SmartAPI -- the rest
of the app (indicators.py, signals.py, notifier.py) doesn't need to change,
as long as you keep returning a DataFrame with columns:
['Open', 'High', 'Low', 'Close', 'Volume'] indexed by datetime.
"""

import pandas as pd
import yfinance as yf

from config import INTERVAL, LOOKBACK_PERIOD


def fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch recent OHLCV candles for a single NSE symbol."""
    df = yf.download(
        tickers=symbol,
        period=LOOKBACK_PERIOD,
        interval=INTERVAL,
        progress=False,
        auto_adjust=True,
    )

    if df.empty:
        raise ValueError(f"No data returned for {symbol}. Check the symbol or your connection.")

    # yfinance sometimes returns MultiIndex columns for single tickers; flatten if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    return df


def fetch_all(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for a list of symbols, skipping any that fail."""
    data = {}
    for symbol in symbols:
        try:
            data[symbol] = fetch_ohlcv(symbol)
        except Exception as exc:
            print(f"[data_fetch] Skipping {symbol}: {exc}")
    return data
