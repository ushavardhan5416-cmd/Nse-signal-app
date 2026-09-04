"""
A minimal backtester: walks forward through history, generating a signal at
each bar using only the data available up to that point, and simulates a
simple "buy on BUY, exit on SELL" long-only strategy.

This is a teaching/sanity-check tool, not a production backtesting engine.
For serious backtesting (slippage, brokerage, position sizing, short
selling), use a dedicated library like vectorbt or backtrader.
"""

import pandas as pd

from config import SMA_LONG
from data_fetch import fetch_ohlcv
from signals import generate_signal


def backtest_symbol(symbol: str, capital: float = 100_000.0) -> dict:
    df = fetch_ohlcv(symbol)
    if len(df) < SMA_LONG + 10:
        raise ValueError(f"Not enough history to backtest {symbol}")

    cash = capital
    shares = 0
    trade_log = []

    # Start after enough bars exist for the longest indicator window
    for i in range(SMA_LONG + 5, len(df)):
        window = df.iloc[: i + 1]
        signal = generate_signal(symbol, window)

        price = signal.price
        if signal.action == "BUY" and shares == 0:
            shares = cash // price
            cash -= shares * price
            trade_log.append((signal.timestamp, "BUY", price, shares))
        elif signal.action == "SELL" and shares > 0:
            cash += shares * price
            trade_log.append((signal.timestamp, "SELL", price, shares))
            shares = 0

    # Close any open position at the last available price
    if shares > 0:
        final_price = df.iloc[-1]["Close"]
        cash += shares * final_price
        trade_log.append((df.index[-1], "SELL (close)", final_price, shares))
        shares = 0

    return {
        "symbol": symbol,
        "start_capital": capital,
        "end_capital": round(cash, 2),
        "return_pct": round((cash - capital) / capital * 100, 2),
        "num_trades": len(trade_log),
        "trade_log": trade_log,
    }


if __name__ == "__main__":
    from config import SYMBOLS

    for sym in SYMBOLS:
        try:
            result = backtest_symbol(sym)
            print(
                f"{result['symbol']}: {result['return_pct']}% return "
                f"over {result['num_trades']} trades "
                f"(₹{result['start_capital']:.0f} -> ₹{result['end_capital']:.0f})"
            )
        except Exception as exc:
            print(f"{sym}: backtest failed -- {exc}")
