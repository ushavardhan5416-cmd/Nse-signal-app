"""
Turns indicator values into discrete signals.

This is intentionally simple and rule-based so it's easy to read, audit, and
extend -- treat it as a starting template, not a proven strategy. Always
backtest before trusting any signal (see backtest.py).
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from chart_patterns import detect_chart_pattern
from config import (
    ADX_THRESHOLD,
    ATR_STOP_MULTIPLIER,
    ATR_TARGET_MULTIPLIER,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    SMA_LONG,
    SMA_SHORT,
    STRIKE_INTERVALS,
    VOLUME_CONFIRMATION_MULTIPLIER,
)
from indicators import add_all_indicators

TOTAL_VOTE_CONDITIONS = 7  # RSI, MACD, SMA trend, breakout, chart pattern, Supertrend flip, VWAP
MIN_VOTES_REQUIRED = 4     # need at least 4 of 7 conditions to agree (~same bar as 3-of-5)


def round_to_strike(symbol: str, price: float) -> int:
    """Round the underlying's price to an approximate ATM strike. Known
    indices use their real strike interval; anything else falls back to a
    rough heuristic based on price magnitude, since actual F&O strike
    intervals vary by stock and aren't available from yfinance."""
    if symbol in STRIKE_INTERVALS:
        interval = STRIKE_INTERVALS[symbol]
    elif price < 500:
        interval = 10
    elif price < 2000:
        interval = 50
    else:
        interval = 100
    return round(price / interval) * interval


@dataclass
class Signal:
    symbol: str
    timestamp: pd.Timestamp
    action: str          # "BUY", "SELL", or "HOLD"
    price: float
    reasons: list[str]
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    option_type: Optional[str] = None    # "CE" or "PE"
    approx_strike: Optional[int] = None
    is_actionable: bool = False  # True only for a confirmed BUY/SELL (4+ of 7 votes)
    triggered_by: list[str] = None       # which of the 7 conditions cast the winning vote (empty for HOLD)
    vote_count: int = 0                  # how many conditions agreed on the winning direction
    total_conditions: int = TOTAL_VOTE_CONDITIONS

    def __post_init__(self):
        if self.triggered_by is None:
            self.triggered_by = []


def generate_signal(symbol: str, df: pd.DataFrame) -> Signal:
    df = add_all_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Each condition below casts at most one vote, as (direction, label).
    # Keeping them in one list (rather than just incrementing counters)
    # lets us report back exactly which conditions drove the final call --
    # see `triggered_by` on the returned Signal.
    votes: list[tuple[str, str]] = []

    # --- RSI: oversold/overbought ---
    if latest["RSI"] < RSI_OVERSOLD:
        votes.append(("bullish", f"RSI oversold ({latest['RSI']:.1f})"))
    elif latest["RSI"] > RSI_OVERBOUGHT:
        votes.append(("bearish", f"RSI overbought ({latest['RSI']:.1f})"))

    # --- MACD: crossover ---
    macd_cross_up = prev["MACD"] < prev["MACD_SIGNAL"] and latest["MACD"] > latest["MACD_SIGNAL"]
    macd_cross_down = prev["MACD"] > prev["MACD_SIGNAL"] and latest["MACD"] < latest["MACD_SIGNAL"]

    if macd_cross_up:
        votes.append(("bullish", "MACD bullish crossover"))
    elif macd_cross_down:
        votes.append(("bearish", "MACD bearish crossover"))

    # --- SMA: trend confirmation ---
    sma_short_col, sma_long_col = f"SMA_{SMA_SHORT}", f"SMA_{SMA_LONG}"
    if latest[sma_short_col] > latest[sma_long_col]:
        votes.append(("bullish", f"SMA{SMA_SHORT} above SMA{SMA_LONG} (uptrend)"))
    else:
        votes.append(("bearish", f"SMA{SMA_SHORT} below SMA{SMA_LONG} (downtrend)"))

    # --- Chart pattern #1: breakout above/below recent swing high/low ---
    # For symbols with real volume data (stocks), a breakout only counts if
    # it's on meaningfully above-average volume -- a breakout on thin volume
    # is much less reliable. Indices report 0 volume via yfinance, so there's
    # nothing meaningful to check there; the volume requirement only applies
    # to stocks (has_volume_data=False skips the check rather than failing it).
    swing_high, swing_low = latest.get("SWING_HIGH"), latest.get("SWING_LOW")
    volume_ma = latest.get("VOLUME_MA")
    has_volume_data = pd.notna(volume_ma) and volume_ma > 0
    volume_confirmed = (latest["Volume"] > volume_ma * VOLUME_CONFIRMATION_MULTIPLIER) if has_volume_data else True
    volume_note = ", volume confirmed" if has_volume_data else ""

    if pd.notna(swing_high) and latest["Close"] > swing_high and volume_confirmed:
        votes.append(("bullish", f"Bullish breakout above swing high ({swing_high:.2f}){volume_note}"))
    elif pd.notna(swing_low) and latest["Close"] < swing_low and volume_confirmed:
        votes.append(("bearish", f"Bearish breakout below swing low ({swing_low:.2f}){volume_note}"))

    # --- Chart pattern #2: classic + candlestick patterns ---
    # Double Top/Bottom, Head & Shoulders, Triangles, and candlestick
    # reversals (Engulfing/Hammer/Shooting Star) -- see chart_patterns.py.
    # This is the 5th vote alongside RSI/MACD/SMA/breakout above.
    pattern_direction, pattern_name = detect_chart_pattern(df)
    if pattern_direction == "bullish":
        votes.append(("bullish", f"Chart pattern: {pattern_name}"))
    elif pattern_direction == "bearish":
        votes.append(("bearish", f"Chart pattern: {pattern_name}"))

    # --- Supertrend: fresh flip in trend direction ---
    # Votes only on the bar the trend actually flips (like the MACD
    # crossover above), not on every bar the trend happens to be up/down --
    # that keeps it a timing signal distinct from the standing SMA filter.
    st_trend, st_prev = latest.get("ST_TREND"), prev.get("ST_TREND")
    if pd.notna(st_trend) and pd.notna(st_prev):
        if st_prev == -1.0 and st_trend == 1.0:
            votes.append(("bullish", "Supertrend flipped bullish"))
        elif st_prev == 1.0 and st_trend == -1.0:
            votes.append(("bearish", "Supertrend flipped bearish"))

    # --- VWAP: price vs session VWAP (intraday fair-value reference) ---
    # Skipped for symbols with no real volume data (indices), same as the
    # breakout volume check -- VWAP is undefined without volume.
    vwap = latest.get("VWAP")
    if pd.notna(vwap):
        if latest["Close"] > vwap:
            votes.append(("bullish", f"Price above VWAP ({vwap:.2f})"))
        else:
            votes.append(("bearish", f"Price below VWAP ({vwap:.2f})"))

    bullish_votes = sum(1 for direction, _ in votes if direction == "bullish")
    bearish_votes = sum(1 for direction, _ in votes if direction == "bearish")
    reasons = [label for _, label in votes]

    # --- Combine votes into an action ---
    # Require at least 4 of the 7 conditions (RSI, MACD, SMA trend, breakout,
    # chart pattern, Supertrend flip, VWAP) to agree before calling BUY/SELL
    # -- otherwise HOLD.
    if bullish_votes >= MIN_VOTES_REQUIRED:
        action = "BUY"
    elif bearish_votes >= MIN_VOTES_REQUIRED:
        action = "SELL"
    else:
        action = "HOLD"

    # --- ADX gate: suppress signals when there's no real trend underway ---
    # ADX measures trend STRENGTH, not direction, so it can't cast a
    # bullish/bearish vote itself -- instead it acts as a final gate on
    # whatever the other 7 conditions decided. A low ADX means the market is
    # flat/choppy, where RSI/MACD/breakout/pattern signals are most prone to
    # whipsawing. Only applied if ADX has enough history to be computed.
    adx = latest.get("ADX")
    if action != "HOLD" and pd.notna(adx) and adx < ADX_THRESHOLD:
        reasons.append(f"Signal suppressed -- ADX {adx:.1f} below {ADX_THRESHOLD} (no strong trend)")
        action = "HOLD"
    elif pd.notna(adx):
        reasons.append(f"ADX {adx:.1f}")

    # Which specific conditions actually drove this call -- e.g. for a BUY,
    # only the conditions that voted "bullish" (a subset of `reasons`, which
    # also includes non-voting notes like the ADX line above).
    if action == "BUY":
        triggered_by, vote_count = [label for d, label in votes if d == "bullish"], bullish_votes
    elif action == "SELL":
        triggered_by, vote_count = [label for d, label in votes if d == "bearish"], bearish_votes
    else:
        triggered_by, vote_count = [], 0

    price = float(latest["Close"])
    atr = latest.get("ATR")

    target_price = None
    stop_loss = None
    option_type = None
    approx_strike = None

    # Always compute a reference target/stop/option view based on whichever
    # direction is currently leaning (even for HOLD, e.g. for on-demand
    # Telegram queries where seeing *some* levels is more useful than none).
    # is_actionable=True only when the full 3-of-5 bar was actually met --
    # that's what scheduled alerts key off of, so HOLD reference levels
    # never trigger a push notification.
    if pd.notna(atr):
        leaning_bullish = bullish_votes >= bearish_votes
        if leaning_bullish:
            target_price = price + atr * ATR_TARGET_MULTIPLIER
            stop_loss = price - atr * ATR_STOP_MULTIPLIER
            option_type = "CE"
        else:
            target_price = price - atr * ATR_TARGET_MULTIPLIER
            stop_loss = price + atr * ATR_STOP_MULTIPLIER
            option_type = "PE"
        approx_strike = round_to_strike(symbol, price)

    return Signal(
        symbol=symbol,
        timestamp=latest.name,
        action=action,
        price=price,
        reasons=reasons,
        target_price=target_price,
        stop_loss=stop_loss,
        option_type=option_type,
        approx_strike=approx_strike,
        is_actionable=(action != "HOLD"),
        triggered_by=triggered_by,
        vote_count=vote_count,
    )


def generate_all_signals(data: dict[str, pd.DataFrame]) -> list[Signal]:
    signals = []
    for symbol, df in data.items():
        if len(df) < SMA_LONG + 5:
            print(f"[signals] Not enough history for {symbol}, skipping.")
            continue
        signals.append(generate_signal(symbol, df))
    return signals
