"""
Fetches OHLCV data for NSE symbols (stocks + indices).

Uses yfinance (free, delayed data -- fine for prototyping/alerts, not for
real-time execution). With 180+ symbols in the watchlist, fetching one at a
time would be slow and risks rate limiting, so this batches requests:
yfinance can download many tickers in a single call and returns a combined
DataFrame with a MultiIndex column structure, which we split back out per
symbol.

For real-time/production use, swap this module for a broker API (Kite
Connect, Upstox, SmartAPI) -- keep the same return shape (a dict of
symbol -> DataFrame with ['Open','High','Low','Close','Volume'] columns)
and the rest of the app doesn't need to change.
"""

import time

import pandas as pd
import yfinance as yf

from config import BATCH_SIZE, INTERVAL, LOOKBACK_PERIOD


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


def fetch_all(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for a list of symbols, batching requests for speed."""
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
    
