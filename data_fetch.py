"""
Fetches OHLCV data for NSE symbols (stocks + indices).

Supports two data sources, switchable via DATA_SOURCE in config.py:
- "yfinance" (default): free, but delayed ~15-20 min. Good for prototyping.
- "angelone": your own Angel One account via SmartAPI, much less delayed.
  See angel_client.py and the README for setup.

Both paths return the exact same shape (a dict of symbol -> DataFrame with
['Open','High','Low','Close','Volume'] columns), so nothing downstream
(indicators, signals, notifier, position_tracker) needs to know or care
which source is actually active.
"""

import time

import pandas as pd
import yfinance as yf

from config import BATCH_SIZE, DATA_SOURCE, INTERVAL, LOOKBACK_PERIOD


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with missing price data, but don't drop rows just because
    Volume is NaN -- indices (Nifty, Bank Nifty, Sensex) commonly report no
    volume via yfinance, and dropping on that column would wipe out all
    index data even though the prices themselves are perfectly valid."""
    df = df.dropna(subset=PRICE_COLUMNS)
    if "Volume" in df.columns:
        df = df.copy()
        df["Volume"] = df["Volume"].fillna(0)
    return df


def _split_batch(df: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Split a multi-ticker yfinance DataFrame into one DataFrame per symbol.

    Important: yfinance still returns MultiIndex columns even for a single
    ticker when group_by='ticker' is passed (which we always do) -- it's
    NOT just a multi-symbol thing. So we detect the actual column structure
    rather than assuming based on len(symbols)."""
    result = {}

    if not isinstance(df.columns, pd.MultiIndex):
        # Only happens if yfinance ever returns flat columns for this call
        single = _clean(df)
        if not single.empty:
            result[symbols[0]] = single
        return result

    for symbol in symbols:
        try:
            sub = _clean(df.xs(symbol, axis=1, level=0))
        except KeyError:
            continue
        if not sub.empty:
            result[symbol] = sub

    return result


def _fetch_all_yfinance(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for a list of symbols via yfinance, batching requests."""
    data = {}

    for batch in _chunk(symbols, BATCH_SIZE):
        try:
            df = yf.download(
                tickers=batch,
                period=LOOKBACK_PERIOD,
                interval=INTERVAL,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:
            print(f"[data_fetch] Batch failed ({batch[0]}..{batch[-1]}): {exc}")
            continue

        if df.empty:
            print(f"[data_fetch] Empty batch response for {batch[0]}..{batch[-1]}")
            continue

        data.update(_split_batch(df, batch))

        # Be a reasonably polite citizen of the free API between batches
        time.sleep(1)

    return data


def fetch_all(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for a list of symbols, from whichever source is
    configured in config.py (DATA_SOURCE)."""
    if DATA_SOURCE == "angelone":
        from angel_client import fetch_all_angelone
        data = fetch_all_angelone(symbols)
    elif DATA_SOURCE == "yfinance":
        data = _fetch_all_yfinance(symbols)
    else:
        raise ValueError(f"Unknown DATA_SOURCE '{DATA_SOURCE}' -- must be 'yfinance' or 'angelone'")

    missing = set(symbols) - set(data.keys())
    if missing:
        print(f"[data_fetch] No data for {len(missing)} symbols: {sorted(missing)[:10]}"
              f"{'...' if len(missing) > 10 else ''}")

    return data


def fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch recent OHLCV candles for a single symbol (used by backtest.py)."""
    result = fetch_all([symbol])
    if symbol not in result:
        raise ValueError(f"No data returned for {symbol}. Check the symbol or your connection.")
    return result[symbol]
