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
)
from indicators import add_all_indicators


@dataclass
class Signal:
    symbol: str
    timestamp: pd.Timestamp
    action: str          # "BUY", "SELL", or "HOLD"
    price: float
    reasons: list[str]
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None


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

    # --- Combine votes into an action ---
    # Require at least 2 of 3 signals to agree before calling BUY/SELL.
    if bullish_votes >= 2 and bullish_votes > bearish_votes:
        action = "BUY"
    elif bearish_votes >= 2 and bearish_votes > bullish_votes:
        action = "SELL"
    else:
        action = "HOLD"

    price = float(latest["Close"])
    atr = latest.get("ATR")

    target_price = None
    stop_loss = None

    # Target/stop are only meaningful for actionable signals, and only when
    # ATR has enough history to be computed (not NaN).
    if action != "HOLD" and pd.notna(atr):
        if action == "BUY":
            target_price = price + atr * ATR_TARGET_MULTIPLIER
            stop_loss = price - atr * ATR_STOP_MULTIPLIER
        elif action == "SELL":
            target_price = price - atr * ATR_TARGET_MULTIPLIER
            stop_loss = price + atr * ATR_STOP_MULTIPLIER

    return Signal(
        symbol=symbol,
        timestamp=latest.name,
        action=action,
        price=price,
        reasons=reasons,
        target_price=target_price,
        stop_loss=stop_loss,
    )


def generate_all_signals(data: dict[str, pd.DataFrame]) -> list[Signal]:
    signals = []
    for symbol, df in data.items():
        if len(df) < SMA_LONG + 5:
            print(f"[signals] Not enough history for {symbol}, skipping.")
            continue
        signals.append(generate_signal(symbol, df))
    return signals
    
