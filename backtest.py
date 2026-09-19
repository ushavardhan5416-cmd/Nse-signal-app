"""
Walks forward through history bar-by-bar for each of config.TRADE_SYMBOLS
(Nifty, Bank Nifty, Sensex), generating a signal at each point using only
data available up to that bar (no lookahead), and simulates the SAME
entry/exit logic the live app actually uses:

- Open a position when a BUY/SELL signal fires (4-of-7 conditions agree,
  see signals.py)
- Exit ONLY when target or stop-loss is hit -- not on the next opposite
  signal
- Only one open position per symbol at a time, matching live behavior
- Checked once per bar using the Close price, matching how the live app
  only checks once per polling cycle -- like the live app, this means an
  intrabar touch-and-reverse between checks can be missed. Deliberate: the
  backtest's blind spots should match the live app's blind spots, rather
  than giving an unrealistically clean read.

IMPORTANT SCOPE NOTE: this backtests the underlying-price signal logic
only (RSI/MACD/SMA/breakout/chart pattern/Supertrend/VWAP on the index
itself) -- it does NOT simulate real option premium P&L. There is no
accessible historical NSE/BSE option-premium data source to backtest
against; yfinance doesn't carry it, and Angel One's historical API mainly
serves recently-listed contracts, not a deep multi-expiry archive. Your
live app's PAPER_TRADING mode is the more trustworthy source for real
options performance, since it accumulates real premium data forward in
time rather than guessing at historical premiums. Treat this backtest as
answering "does the underlying signal logic have any edge", not "what
would my options P&L have been."

This is a teaching/sanity-check tool, not a production backtesting engine.
"""

import pandas as pd

from config import SMA_LONG, TRADE_SYMBOLS
from data_fetch import fetch_ohlcv
from signals import generate_signal


def backtest_symbol(symbol: str) -> dict:
    df = fetch_ohlcv(symbol)
    min_bars = SMA_LONG + 10
    if len(df) < min_bars:
        raise ValueError(f"Not enough history to backtest {symbol} "
                          f"(have {len(df)} bars, need at least {min_bars})")

    trades = []
    open_position = None  # dict(action, entry_price, target, stop, opened_at) or None

    for i in range(SMA_LONG + 5, len(df)):
        window = df.iloc[: i + 1]
        signal = generate_signal(symbol, window)
        price = signal.price

        # Check the open position (if any) against this bar's price first --
        # mirrors main.py's order: check existing positions before opening
        # new ones.
        if open_position is not None:
            hit = None
            if open_position["action"] == "BUY":
                if price >= open_position["target"]:
                    hit = "TARGET"
                elif price <= open_position["stop"]:
                    hit = "STOP"
            else:  # SELL
                if price <= open_position["target"]:
                    hit = "TARGET"
                elif price >= open_position["stop"]:
                    hit = "STOP"

            if hit:
                trades.append({
                    "action": open_position["action"],
                    "entry_price": open_position["entry_price"],
                    "exit_price": price,
                    "result": hit,
                    "vote_count": open_position["vote_count"],
                    "triggered_by": open_position["triggered_by"],
                    "opened_at": open_position["opened_at"],
                    "closed_at": signal.timestamp,
                })
                open_position = None

        # Open a new position if a fresh signal fires and nothing's open
        if open_position is None and signal.is_actionable:
            open_position = {
                "action": signal.action,
                "entry_price": signal.price,
                "target": signal.target_price,
                "stop": signal.stop_loss,
                "vote_count": signal.vote_count,
                "triggered_by": list(signal.triggered_by),
                "opened_at": signal.timestamp,
            }

    wins = sum(1 for t in trades if t["result"] == "TARGET")
    losses = sum(1 for t in trades if t["result"] == "STOP")
    total = len(trades)
    win_rate = (wins / total * 100) if total else 0.0

    return {
        "symbol": symbol,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "still_open": open_position is not None,
        "trades": trades,
    }


if __name__ == "__main__":
    all_results = []
    for sym in TRADE_SYMBOLS:
        try:
            result = backtest_symbol(sym)
            all_results.append(result)
            open_note = " (1 position still open at end of data)" if result["still_open"] else ""
            print(
                f"{result['symbol']}: {result['total_trades']} trades -- "
                f"{result['wins']} target hits, {result['losses']} stop hits "
                f"({result['win_rate']}% win rate){open_note}"
            )
            for t in result["trades"]:
                print(
                    f"    {t['opened_at']} {t['action']} @ {t['entry_price']:.2f} "
                    f"[{t['vote_count']}/7: {', '.join(t['triggered_by'][:3])}...] "
                    f"-> {t['result']} @ {t['exit_price']:.2f} ({t['closed_at']})"
                )
        except Exception as exc:
            print(f"{sym}: backtest failed -- {exc}")

    if all_results:
        total_trades = sum(r["total_trades"] for r in all_results)
        total_wins = sum(r["wins"] for r in all_results)
        total_losses = sum(r["losses"] for r in all_results)
        overall_rate = (total_wins / total_trades * 100) if total_trades else 0.0
        print()
        print(f"OVERALL (underlying signal logic only, NOT real option P&L): "
              f"{total_trades} trades across {len(all_results)} symbols -- "
              f"{total_wins} wins, {total_losses} losses ({overall_rate:.1f}% win rate)")
        print()
        print("Reminder: this backtests whether the signal logic calls direction correctly")
        print("on the underlying. It does NOT reflect real option premium P&L -- your live")
        print("PAPER_TRADING mode is the trustworthy source for that.")
