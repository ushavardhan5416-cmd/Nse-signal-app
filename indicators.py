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
    ST_MULTIPLIER,
    ST_PERIOD,
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


def add_supertrend(df: pd.DataFrame, period: int = ST_PERIOD, multiplier: float = ST_MULTIPLIER) -> pd.DataFrame:
    """Supertrend -- an ATR-based trend-following line. Unlike ATR itself,
    the bands are path-dependent (each band can only tighten toward price,
    never loosen, until price actually crosses it) so this is computed with
    an explicit loop rather than vectorized pandas ops. Adds ST_TREND: +1
    for uptrend, -1 for downtrend, NaN until enough bars exist to seed it."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=period).mean()

    hl2 = (high + low) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = pd.Series(index=df.index, dtype="float64")
    final_lower = pd.Series(index=df.index, dtype="float64")
    trend = pd.Series(index=df.index, dtype="float64")  # +1 uptrend, -1 downtrend

    first_valid = atr.first_valid_index()
    if first_valid is None:
        df["ST_TREND"] = trend
        return df

    start_pos = df.index.get_loc(first_valid)
    final_upper.iloc[start_pos] = basic_upper.iloc[start_pos]
    final_lower.iloc[start_pos] = basic_lower.iloc[start_pos]
    trend.iloc[start_pos] = 1.0  # arbitrary seed direction; settles within a few bars

    for i in range(start_pos + 1, len(df)):
        bu, bl = basic_upper.iloc[i], basic_lower.iloc[i]
        prev_fu, prev_fl = final_upper.iloc[i - 1], final_lower.iloc[i - 1]
        prev_close_i = close.iloc[i - 1]

        fu = bu if (bu < prev_fu or prev_close_i > prev_fu) else prev_fu
        fl = bl if (bl > prev_fl or prev_close_i < prev_fl) else prev_fl
        final_upper.iloc[i] = fu
        final_lower.iloc[i] = fl

        prev_trend = trend.iloc[i - 1]
        if prev_trend == 1.0:
            trend.iloc[i] = -1.0 if close.iloc[i] < fl else 1.0
        else:
            trend.iloc[i] = 1.0 if close.iloc[i] > fu else -1.0

    df["ST_TREND"] = trend
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Volume Weighted Average Price, reset each trading session (day) --
    the standard convention, since VWAP is an intraday fair-value reference,
    not a rolling multi-day average. Symbols with no real volume data
    (indices report 0 via yfinance) end up with VWAP == NaN for the whole
    session; signals.py detects this and skips the VWAP vote for them."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    session = pd.Series(df.index, index=df.index).dt.date
    tpv = typical_price * df["Volume"]
    cum_tpv = tpv.groupby(session).cumsum()
    cum_vol = df["Volume"].groupby(session).cumsum()
    df["VWAP"] = cum_tpv / cum_vol.replace(0, pd.NA)
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
    df = add_supertrend(df)
    df = add_vwap(df)
    df = add_volume_ma(df)
    return df
