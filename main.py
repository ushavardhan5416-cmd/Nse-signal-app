"""
Entry point: runs a polling loop that fetches data, generates signals, and
sends alerts. This is alerts-only -- it never places orders. Run this during
market hours (NSE: 9:15 AM - 3:30 PM IST, Mon-Fri).
"""

import time
from datetime import datetime

from config import POLL_INTERVAL_SECONDS, SYMBOLS
from data_fetch import fetch_all
from notifier import notify_signals
from signals import generate_all_signals


def run_once() -> None:
    print(f"\n[{datetime.now()}] Fetching data for {len(SYMBOLS)} symbols...")
    data = fetch_all(SYMBOLS)

    if not data:
        print("[main] No data fetched this cycle, skipping.")
        return

    signals = generate_all_signals(data)

    for s in signals:
        levels = ""
        if s.target_price is not None and s.stop_loss is not None:
            levels = f"  target={s.target_price:.2f}  stop={s.stop_loss:.2f}"
        print(f"  {s.symbol}: {s.action} @ {s.price:.2f}{levels}  ({', '.join(s.reasons)})")

    notify_signals(signals, only_actionable=True)


def run_loop() -> None:
    print("Starting NSE signals app. Press Ctrl+C to stop.")
    while True:
        try:
            run_once()
        except Exception as exc:
            print(f"[main] Error during cycle: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_loop()
    
