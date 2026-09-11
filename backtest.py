"""
Walks forward through history bar-by-bar, generating a signal at each point
using only data available up to that bar (no lookahead), and simulates the
SAME entry/exit logic the live app actually uses (see position_tracker.py):

- Open a position when a BUY/SELL signal fires (4-of-7 conditions agree)
- Exit ONLY when target or stop-loss is hit -- not on the next opposite
  signal, which is what earlier versions of this backtest did
- Only one open position per symbol at a time, matching live behavior
- Checked once per bar using the Close price, matching how the live app
  only checks once per 15-min cycle -- this means, like the live app, an
  intrabar touch-and-reverse of target/stop between checks can be missed.
  This is a deliberate simplification so the backtest's blind spots match
  the live app's blind spots, rather than giving an unrealistically clean
  read.

This is a teaching/sanity-check tool, not a production backtesting engine.
For serious backtesting (slippage, brokerage, realistic fills), use a
dedicated library like vectorbt or backtrader.
"""

import pandas as pd

from config import SMA_LONG
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
        # mirrors main.py's order: check_positions() before open_position().
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
    from config import SYMBOLS

    all_results = []
    for sym in SYMBOLS:
        try:
            result = backtest_symbol(sym)
            all_results.append(result)
            open_note = " (1 position still open at end of data)" if result["still_open"] else ""
            print(
                f"{result['symbol']}: {result['total_trades']} trades -- "
                f"{result['wins']} target hits, {result['losses']} stop hits "
                f"({result['win_rate']}% win rate){open_note}"
            )
        except Exception as exc:
            print(f"{sym}: backtest failed -- {exc}")

    if all_results:
        total_trades = sum(r["total_trades"] for r in all_results)
        total_wins = sum(r["wins"] for r in all_results)
        total_losses = sum(r["losses"] for r in all_results)
        overall_rate = (total_wins / total_trades * 100) if total_trades else 0.0
        print()
        print(f"OVERALL: {total_trades} trades across {len(all_results)} symbols -- "
              f"{total_wins} wins, {total_losses} losses ({overall_rate:.1f}% win rate)")
