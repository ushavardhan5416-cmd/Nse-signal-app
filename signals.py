"""
Turns indicator values into discrete signals.

This is intentionally simple and rule-based so it's easy to read, audit, and
extend -- treat it as a starting template, not a proven strategy. Always
backtest before trusting any signal (see backtest.py).
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config import (
    ATR_STOP_MULTIPLIER,
    ATR_TARGET_MULTIPLIER,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    SMA_LONG,
    SMA_SHORT,
    STRIKE_INTERVALS,
)
from indicators import add_all_indicators

MIN_VOTES_REQUIRED = 3  # need at least 3 of 4 conditions to agree


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
    is_actionable: bool = False  # True only for a confirmed BUY/SELL (3+ votes)


def generate_signal(symbol: str, df: pd.DataFrame) -> Signal:
    df = add_all_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    reasons = []
    bullish_votes = 0
    bearish_votes = 0

    # --- RSI: oversold/overbought ---
    if latest["RSI"] < RSI_OVERSOLD:
        bullish_votes += 1
        reasons.append(f"RSI oversold ({latest['RSI']:.1f})")
    elif latest["RSI"] > RSI_OVERBOUGHT:
        bearish_votes += 1
        reasons.append(f"RSI overbought ({latest['RSI']:.1f})")

    # --- MACD: crossover ---
    macd_cross_up = prev["MACD"] < prev["MACD_SIGNAL"] and latest["MACD"] > latest["MACD_SIGNAL"]
    macd_cross_down = prev["MACD"] > prev["MACD_SIGNAL"] and latest["MACD"] < latest["MACD_SIGNAL"]

    if macd_cross_up:
        bullish_votes += 1
        reasons.append("MACD bullish crossover")
    elif macd_cross_down:
        bearish_votes += 1
        reasons.append("MACD bearish crossover")

    # --- SMA: trend confirmation ---
    sma_short_col, sma_long_col = f"SMA_{SMA_SHORT}", f"SMA_{SMA_LONG}"
    if latest[sma_short_col] > latest[sma_long_col]:
        bullish_votes += 1
        reasons.append(f"SMA{SMA_SHORT} above SMA{SMA_LONG} (uptrend)")
    else:
        bearish_votes += 1
        reasons.append(f"SMA{SMA_SHORT} below SMA{SMA_LONG} (downtrend)")

    # --- Chart pattern: breakout above/below recent swing high/low ---
    swing_high, swing_low = latest.get("SWING_HIGH"), latest.get("SWING_LOW")
    if pd.notna(swing_high) and latest["Close"] > swing_high:
        bullish_votes += 1
        reasons.append(f"Bullish breakout above swing high ({swing_high:.2f})")
    elif pd.notna(swing_low) and latest["Close"] < swing_low:
        bearish_votes += 1
        reasons.append(f"Bearish breakout below swing low ({swing_low:.2f})")

    # --- Combine votes into an action ---
    # Require at least 3 of the 4 conditions (RSI, MACD, SMA trend, breakout)
    # to agree before calling BUY/SELL -- otherwise HOLD.
    if bullish_votes >= MIN_VOTES_REQUIRED:
        action = "BUY"
    elif bearish_votes >= MIN_VOTES_REQUIRED:
        action = "SELL"
    else:
        action = "HOLD"

    price = float(latest["Close"])
    atr = latest.get("ATR")

    target_price = None
    stop_loss = None
    option_type = None
    approx_strike = None

    # Always compute a reference target/stop/option view based on whichever
    # direction is currently leaning (even for HOLD, e.g. for on-demand
    # Telegram queries where seeing *some* levels is more useful than none).
    # is_actionable=True only when the full 3-of-4 bar was actually met --
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
    )


def generate_all_signals(data: dict[str, pd.DataFrame]) -> list[Signal]:
    signals = []
    for symbol, df in data.items():
        if len(df) < SMA_LONG + 5:
            print(f"[signals] Not enough history for {symbol}, skipping.")
            continue
        signals.append(generate_signal(symbol, df))
    return signals
    
