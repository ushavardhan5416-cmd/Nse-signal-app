"""
Classic and candlestick chart-pattern detection.

This feeds the 5th vote in signals.py, alongside RSI / MACD / SMA trend /
swing breakout. Chart-pattern recognition is inherently a judgment call even
for a human trader looking at a chart, so treat these as heuristic, best-effort
detectors -- one vote among five, not a standalone strategy. Every classic
pattern here requires a *confirmed break* of its key level (neckline /
trendline) before it votes; a pattern that's still "forming" does not count,
which cuts down on false positives at the cost of flagging things a little
later than a human chartist eyeballing the same candles might.

Patterns covered:
  - Double Top / Double Bottom
  - Head & Shoulders (and Inverse)
  - Triangles (ascending / descending / symmetrical)
  - Candlestick reversals: Bullish/Bearish Engulfing, Hammer, Shooting Star

Detection approach: bars are first reduced to "swing pivots" (local
high/low points confirmed by a few bars on either side -- see find_pivots),
then the classic patterns are just specific arrangements of 2-3 recent
pivots. This keeps everything computable directly from OHLC data, no peak
libraries required.
"""

import numpy as np
import pandas as pd

from config import (
    PATTERN_LOOKBACK,
    PATTERN_PIVOT_WINDOW,
    PATTERN_PRICE_TOLERANCE,
    PATTERN_TRIANGLE_MIN_TOUCHES,
)


def find_pivots(df: pd.DataFrame, window: int = PATTERN_PIVOT_WINDOW) -> tuple[pd.Series, pd.Series]:
    """Mark bars whose High/Low is the single extreme within a +/- `window`
    bar neighborhood ("swing pivots"). Note this means the most recent
    `window` bars can never be confirmed as pivots yet -- a swing point can
    only be identified in hindsight, once later bars exist to compare against."""
    highs, lows = df["High"], df["Low"]
    pivot_high = pd.Series(False, index=df.index)
    pivot_low = pd.Series(False, index=df.index)

    for i in range(window, len(df) - window):
        seg_h = highs.iloc[i - window: i + window + 1]
        seg_l = lows.iloc[i - window: i + window + 1]
        if highs.iloc[i] == seg_h.max() and (seg_h == seg_h.max()).sum() == 1:
            pivot_high.iloc[i] = True
        if lows.iloc[i] == seg_l.min() and (seg_l == seg_l.min()).sum() == 1:
            pivot_low.iloc[i] = True

    return pivot_high, pivot_low


def _pivot_points(df: pd.DataFrame, mask: pd.Series, price_col: str) -> list[tuple[int, float]]:
    """Return [(bar_position, price)] for every pivot in `mask`, oldest first.
    bar_position is a 0-based index into `df` (not a timestamp), which makes
    ordering/spacing checks between pivots simple."""
    positions = np.where(mask.values)[0]
    return [(int(pos), float(df[price_col].iloc[pos])) for pos in positions]


def detect_double_top_bottom(
    df: pd.DataFrame,
    pivot_high: pd.Series,
    pivot_low: pd.Series,
    tolerance: float = PATTERN_PRICE_TOLERANCE,
) -> tuple[str | None, str | None]:
    highs = _pivot_points(df, pivot_high, "High")
    lows = _pivot_points(df, pivot_low, "Low")
    latest_close = float(df["Close"].iloc[-1])

    # Double Top: two similar-height peaks with a trough between them (the
    # "neckline"). Confirmed bearish once price closes below that neckline.
    if len(highs) >= 2:
        (pos1, price1), (pos2, price2) = highs[-2], highs[-1]
        between = [p for p in lows if pos1 < p[0] < pos2]
        if between and abs(price1 - price2) / price1 <= tolerance:
            neckline = min(p[1] for p in between)
            if latest_close < neckline:
                return "bearish", f"Double Top confirmed (peaks ~{price1:.2f}/{price2:.2f}, broke neckline {neckline:.2f})"

    # Double Bottom: mirror image -- two similar-depth troughs with a peak
    # between them, confirmed bullish once price closes above that neckline.
    if len(lows) >= 2:
        (pos1, price1), (pos2, price2) = lows[-2], lows[-1]
        between = [p for p in highs if pos1 < p[0] < pos2]
        if between and abs(price1 - price2) / price1 <= tolerance:
            neckline = max(p[1] for p in between)
            if latest_close > neckline:
                return "bullish", f"Double Bottom confirmed (troughs ~{price1:.2f}/{price2:.2f}, broke neckline {neckline:.2f})"

    return None, None


def detect_head_and_shoulders(
    df: pd.DataFrame,
    pivot_high: pd.Series,
    pivot_low: pd.Series,
    tolerance: float = PATTERN_PRICE_TOLERANCE,
) -> tuple[str | None, str | None]:
    highs = _pivot_points(df, pivot_high, "High")
    lows = _pivot_points(df, pivot_low, "Low")
    latest_close = float(df["Close"].iloc[-1])

    # Head & Shoulders (bearish): shoulder-head-shoulder peaks, with the head
    # clearly taller than two roughly-equal shoulders, confirmed by a close
    # below the neckline (the two troughs between the peaks).
    if len(highs) >= 3:
        (pos_l, left), (pos_h, head), (pos_r, right) = highs[-3:]
        shoulders_match = abs(left - right) / left <= tolerance
        head_taller = head > left * (1 + tolerance) and head > right * (1 + tolerance)
        neck = [p for p in lows if pos_l < p[0] < pos_r]
        if shoulders_match and head_taller and len(neck) >= 2:
            neckline = (neck[0][1] + neck[-1][1]) / 2
            if latest_close < neckline:
                return "bearish", f"Head & Shoulders confirmed (head {head:.2f}, neckline ~{neckline:.2f})"

    # Inverse Head & Shoulders (bullish): mirror image using troughs.
    if len(lows) >= 3:
        (pos_l, left), (pos_h, head), (pos_r, right) = lows[-3:]
        shoulders_match = abs(left - right) / left <= tolerance
        head_deeper = head < left * (1 - tolerance) and head < right * (1 - tolerance)
        neck = [p for p in highs if pos_l < p[0] < pos_r]
        if shoulders_match and head_deeper and len(neck) >= 2:
            neckline = (neck[0][1] + neck[-1][1]) / 2
            if latest_close > neckline:
                return "bullish", f"Inverse Head & Shoulders confirmed (head {head:.2f}, neckline ~{neckline:.2f})"

    return None, None


def detect_triangle(
    df: pd.DataFrame,
    pivot_high: pd.Series,
    pivot_low: pd.Series,
    min_touches: int = PATTERN_TRIANGLE_MIN_TOUCHES,
) -> tuple[str | None, str | None]:
    highs = _pivot_points(df, pivot_high, "High")
    lows = _pivot_points(df, pivot_low, "Low")
    if len(highs) < min_touches or len(lows) < min_touches:
        return None, None

    highs = highs[-min_touches:]
    lows = lows[-min_touches:]

    hx = np.array([p[0] for p in highs], dtype=float)
    hy = np.array([p[1] for p in highs], dtype=float)
    lx = np.array([p[0] for p in lows], dtype=float)
    ly = np.array([p[1] for p in lows], dtype=float)

    # Fit a straight line through the recent swing highs (resistance) and
    # through the recent swing lows (support). The slope tells us whether
    # each trendline is flat, rising, or falling.
    high_slope, high_intercept = np.polyfit(hx, hy, 1)
    low_slope, low_intercept = np.polyfit(lx, ly, 1)

    latest_pos = len(df) - 1
    latest_close = float(df["Close"].iloc[-1])
    resistance_now = high_slope * latest_pos + high_intercept
    support_now = low_slope * latest_pos + low_intercept

    # "Flat" is relative to price level, not an absolute number -- a slope
    # under ~0.05% of price per bar is treated as flat.
    flat_threshold = latest_close * 0.0005
    flat_high = abs(high_slope) < flat_threshold
    flat_low = abs(low_slope) < flat_threshold
    rising_low = low_slope >= flat_threshold
    falling_high = high_slope <= -flat_threshold

    # Ascending triangle: flat resistance + rising support -- bullish bias,
    # confirmed on a breakout above the flat resistance line.
    if flat_high and rising_low and latest_close > resistance_now:
        return "bullish", f"Ascending Triangle breakout above resistance ~{resistance_now:.2f}"

    # Descending triangle: flat support + falling resistance -- bearish
    # bias, confirmed on a breakdown below the flat support line.
    if flat_low and falling_high and latest_close < support_now:
        return "bearish", f"Descending Triangle breakdown below support ~{support_now:.2f}"

    # Symmetrical triangle: both lines converging (resistance falling,
    # support rising) -- direction is only known once one line breaks.
    if falling_high and rising_low:
        if latest_close > resistance_now:
            return "bullish", f"Symmetrical Triangle breakout above ~{resistance_now:.2f}"
        if latest_close < support_now:
            return "bearish", f"Symmetrical Triangle breakdown below ~{support_now:.2f}"

    return None, None


def detect_candlestick_pattern(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Single/two-candle reversal patterns on the latest bar. These are the
    noisiest of the patterns here (especially on short intraday timeframes),
    so they only fire as a last resort when no classic pattern above has
    already confirmed -- see detect_chart_pattern()."""
    if len(df) < 7:
        return None, None

    latest, prev = df.iloc[-1], df.iloc[-2]
    body = abs(latest["Close"] - latest["Open"])
    candle_range = latest["High"] - latest["Low"]
    if candle_range <= 0 or body <= 0:
        return None, None

    upper_wick = latest["High"] - max(latest["Close"], latest["Open"])
    lower_wick = min(latest["Close"], latest["Open"]) - latest["Low"]

    prev_bearish = prev["Close"] < prev["Open"]
    prev_bullish = prev["Close"] > prev["Open"]
    curr_bullish = latest["Close"] > latest["Open"]
    curr_bearish = latest["Close"] < latest["Open"]

    # Crude prior-trend context (net direction over the 5 bars before this
    # one) -- hammers/shooting stars are only meaningful as *reversals* of
    # an existing move, not in isolation.
    prior_window = df["Close"].iloc[-7:-1]
    prior_trend_down = prior_window.iloc[-1] < prior_window.iloc[0]
    prior_trend_up = prior_window.iloc[-1] > prior_window.iloc[0]

    if prev_bearish and curr_bullish and latest["Open"] <= prev["Close"] and latest["Close"] >= prev["Open"]:
        return "bullish", "Bullish Engulfing"
    if prev_bullish and curr_bearish and latest["Open"] >= prev["Close"] and latest["Close"] <= prev["Open"]:
        return "bearish", "Bearish Engulfing"
    if prior_trend_down and lower_wick >= body * 2 and upper_wick <= body * 0.5:
        return "bullish", "Hammer"
    if prior_trend_up and upper_wick >= body * 2 and lower_wick <= body * 0.5:
        return "bearish", "Shooting Star"

    return None, None


def detect_chart_pattern(
    df: pd.DataFrame,
    pivot_window: int = PATTERN_PIVOT_WINDOW,
    lookback: int = PATTERN_LOOKBACK,
    tolerance: float = PATTERN_PRICE_TOLERANCE,
    min_touches: int = PATTERN_TRIANGLE_MIN_TOUCHES,
) -> tuple[str | None, str | None]:
    """Run every pattern detector against the most recent `lookback` bars and
    return the first confirmed hit as (direction, pattern_name), or
    (None, None) if nothing confirmed.

    Priority order (strongest/least-noisy first): Head & Shoulders, Double
    Top/Bottom, Triangles, then candlestick patterns as a fallback -- this
    matches how reliable each pattern type is to detect mechanically from
    OHLC data alone (see chart_patterns.py module docstring).
    """
    needed = lookback + (2 * pivot_window)
    if len(df) < needed:
        return None, None

    recent = df.tail(needed)
    pivot_high, pivot_low = find_pivots(recent, pivot_window)

    for direction, name in (
        detect_head_and_shoulders(recent, pivot_high, pivot_low, tolerance),
        detect_double_top_bottom(recent, pivot_high, pivot_low, tolerance),
        detect_triangle(recent, pivot_high, pivot_low, min_touches),
        detect_candlestick_pattern(recent),
    ):
        if direction:
            return direction, name

    return None, None
