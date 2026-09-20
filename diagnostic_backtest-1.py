"""
Diagnostic tool: runs the SAME backtest logic as backtest.py, but repeats
it at several different MIN_VOTES_REQUIRED thresholds (by temporarily
monkey-patching the value in memory) to see how much signal frequency and
win rate change as the bar is loosened.

This does NOT modify signals.py on disk or change your live app's
behavior in any way -- it's purely a read-only diagnostic. Run it, look at
the numbers, then decide for yourself whether the live 4-of-7 threshold is
well-calibrated or overly strict, and manually adjust signals.py if you
want to change it.

Same scope note as backtest.py: this tests the underlying-price signal
logic only, not real option premium P&L.
"""

import signals
from config import SMA_LONG, TRADE_SYMBOLS
from data_fetch import fetch_ohlcv

THRESHOLDS_TO_TEST = [2, 3, 4]  # out of 7 total conditions
ORIGINAL_VOTE_THRESHOLD = signals.MIN_VOTES_REQUIRED
ORIGINAL_ADX_THRESHOLD = signals.ADX_THRESHOLD

# Second sweep: at the loosest vote threshold, does the ADX gate turn out
# to be the real bottleneck? ADX_THRESHOLD=0 effectively disables the gate
# (every ADX value is >= 0, so it never suppresses a signal).
ADX_THRESHOLDS_TO_TEST = [ORIGINAL_ADX_THRESHOLD, 15, 0]


def backtest_symbol_at_threshold(symbol: str, threshold: int, df, adx_threshold: float = None) -> dict:
    """Same walk-forward logic as backtest.py's backtest_symbol(), but
    takes a pre-fetched df (so we only fetch each symbol's data once,
    not once per threshold/combination) and given vote/ADX thresholds."""
    signals.MIN_VOTES_REQUIRED = threshold
    if adx_threshold is not None:
        signals.ADX_THRESHOLD = adx_threshold

    trades = []
    open_position = None

    for i in range(SMA_LONG + 5, len(df)):
        window = df.iloc[: i + 1]
        signal = signals.generate_signal(symbol, window)
        price = signal.price

        if open_position is not None:
            hit = None
            if open_position["action"] == "BUY":
                if price >= open_position["target"]:
                    hit = "TARGET"
                elif price <= open_position["stop"]:
                    hit = "STOP"
            else:
                if price <= open_position["target"]:
                    hit = "TARGET"
                elif price >= open_position["stop"]:
                    hit = "STOP"

            if hit:
                trades.append({"result": hit})
                open_position = None

        if open_position is None and signal.is_actionable:
            open_position = {
                "action": signal.action,
                "target": signal.target_price,
                "stop": signal.stop_loss,
            }

    wins = sum(1 for t in trades if t["result"] == "TARGET")
    losses = sum(1 for t in trades if t["result"] == "STOP")
    total = len(trades)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "still_open": open_position is not None,
    }


if __name__ == "__main__":
    print(f"Diagnostic backtest -- testing vote thresholds {THRESHOLDS_TO_TEST} out of 7 conditions")
    print(f"(live app is currently set to {ORIGINAL_VOTE_THRESHOLD}-of-7, ADX_THRESHOLD={ORIGINAL_ADX_THRESHOLD})")
    print("This does NOT change your live signals.py -- read-only diagnostic.\n")

    # Fetch each symbol's data once, reuse across every combination tested below
    symbol_data = {}
    for sym in TRADE_SYMBOLS:
        try:
            symbol_data[sym] = fetch_ohlcv(sym)
        except Exception as exc:
            print(f"{sym}: data fetch failed -- {exc}")

    def run_sweep(label, threshold, adx_threshold):
        print(f"--- {label} ---")
        total_trades = total_wins = total_losses = 0
        for sym, df in symbol_data.items():
            try:
                result = backtest_symbol_at_threshold(sym, threshold, df, adx_threshold)
            except Exception as exc:
                print(f"  {sym}: failed -- {exc}")
                continue
            open_note = " (1 still open)" if result["still_open"] else ""
            print(f"  {sym}: {result['total_trades']} trades -- "
                  f"{result['wins']}W/{result['losses']}L "
                  f"({result['win_rate']}% win rate){open_note}")
            total_trades += result["total_trades"]
            total_wins += result["wins"]
            total_losses += result["losses"]
        overall_rate = round(total_wins / total_trades * 100, 1) if total_trades else 0.0
        print(f"  OVERALL: {total_trades} trades, {total_wins}W/{total_losses}L ({overall_rate}% win rate)\n")

    try:
        # Sweep 1: vote threshold alone (ADX gate stays at its live setting)
        for threshold in THRESHOLDS_TO_TEST:
            run_sweep(f"{threshold}-of-7 (ADX gate at live setting, {ORIGINAL_ADX_THRESHOLD})", threshold, ORIGINAL_ADX_THRESHOLD)

        # Sweep 2: at the loosest vote threshold, isolate the ADX gate's own
        # effect -- if loosening ADX unlocks meaningfully more trades where
        # sweep 1 didn't, the ADX gate (not vote count) is the real bottleneck.
        loosest_vote_threshold = min(THRESHOLDS_TO_TEST)
        for adx_threshold in ADX_THRESHOLDS_TO_TEST:
            note = " (live setting)" if adx_threshold == ORIGINAL_ADX_THRESHOLD else ""
            run_sweep(f"{loosest_vote_threshold}-of-7, ADX_THRESHOLD={adx_threshold}{note}",
                      loosest_vote_threshold, adx_threshold)
    finally:
        # Always restore both real settings, even if something above raised
        signals.MIN_VOTES_REQUIRED = ORIGINAL_VOTE_THRESHOLD
        signals.ADX_THRESHOLD = ORIGINAL_ADX_THRESHOLD
        print(f"Restored MIN_VOTES_REQUIRED to {ORIGINAL_VOTE_THRESHOLD} and "
              f"ADX_THRESHOLD to {ORIGINAL_ADX_THRESHOLD} (live app settings, unaffected by this script)")
