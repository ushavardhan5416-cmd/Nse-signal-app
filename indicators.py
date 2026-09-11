"""
Technical indicator calculations, implemented directly on top of pandas so
the project has no hard dependency on ta-lib (which needs a compiled C
library). Swap in pandas-ta or ta-lib later if you want a wider indicator set.
"""

import pandas as pd

from config import (
    ADX_PERIOD,
    ATR_PERIOD,
    BREAKOUT_LOOKBACK,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_PERIOD,
    SMA_LONG,
    SMA_SHORT,
    VOLUME_MA_PERIOD,
)


def add_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> pd.DataFrame:
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()

    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=signal, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]
    return df


def add_sma(df: pd.DataFrame, short: int = SMA_SHORT, long: int = SMA_LONG) -> pd.DataFrame:
    df[f"SMA_{short}"] = df["Close"].rolling(window=short).mean()
    df[f"SMA_{long}"] = df["Close"].rolling(window=long).mean()
    return df


def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    """Average True Range -- a volatility measure used to size targets/stops
    relative to how much each symbol actually moves, rather than a fixed %."""
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["ATR"] = true_range.rolling(window=period, min_periods=period).mean()
    return df


def add_breakout_levels(df: pd.DataFrame, lookback: int = BREAKOUT_LOOKBACK) -> pd.DataFrame:
    """Rolling swing high/low over the prior `lookback` candles (excluding the
    current one), used to detect breakout chart patterns -- price closing
    above recent resistance (bullish) or below recent support (bearish)."""
    df["SWING_HIGH"] = df["High"].shift(1).rolling(window=lookback, min_periods=lookback).max()
    df["SWING_LOW"] = df["Low"].shift(1).rolling(window=lookback, min_periods=lookback).min()
    return df


def add_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.DataFrame:
    """Average Directional Index -- measures trend STRENGTH (not direction).
    Used as a gate: signals are suppressed when ADX is low (choppy/flat
    market), regardless of what RSI/MACD/SMA/breakout say. Standard
    Wilder's-smoothing implementation."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move[(up_move > down_move) & (up_move > 0)]
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move[(down_move > up_move) & (down_move > 0)]

    # Wilder's smoothing = an EMA with alpha = 1/period
    atr_smooth = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * (plus_dm_smooth / atr_smooth)
    minus_di = 100 * (minus_dm_smooth / atr_smooth)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["ADX"] = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return df


def add_volume_ma(df: pd.DataFrame, period: int = VOLUME_MA_PERIOD) -> pd.DataFrame:
    """Rolling average volume, used to confirm breakouts happen on
    meaningfully above-average volume rather than a thin, low-conviction
    move. Symbols with no real volume data (indices report 0 via yfinance)
    will naturally have VOLUME_MA == 0 -- signals.py detects this and skips
    the volume check for those symbols rather than blocking them entirely."""
    df["VOLUME_MA"] = df["Volume"].rolling(window=period, min_periods=period).mean()
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = add_rsi(df)
    df = add_macd(df)
    df = add_sma(df)
    df = add_atr(df)
    df = add_breakout_levels(df)
    df = add_adx(df)
    df = add_volume_ma(df)
    return df
