"""
Entry point: runs a polling loop that fetches data, generates signals, and
sends alerts. This is alerts-only -- it never places orders. The cycle only
runs within the configured alert window (see config.py / market_hours.py),
regardless of what timezone the server itself is in.

Also starts a background thread that listens for on-demand Telegram queries
(e.g. sending "RELIANCE" to the bot to check its signal right now, outside
the normal schedule) -- see telegram_listener.py.
"""

import threading
import time

from config import POLL_INTERVAL_SECONDS, SYMBOLS
from data_fetch import fetch_all
from market_hours import is_within_alert_window, now_ist
from notifier import notify_signals
from signals import generate_all_signals
from telegram_listener import run_listener


def run_once() -> None:
    if not is_within_alert_window():
        print(f"[{now_ist()}] Outside alert window (trading days, configured "
              f"hours only) -- skipping this cycle.")
        return

    print(f"\n[{now_ist()}] Fetching data for {len(SYMBOLS)} symbols...")
    data = fetch_all(SYMBOLS)

    if not data:
        print("[main] No data fetched this cycle, skipping.")
        return

    signals = generate_all_signals(data)

    for s in signals:
        levels = ""
        if s.target_price is not None and s.stop_loss is not None:
            levels = f"  target={s.target_price:.2f}  stop={s.stop_loss:.2f}"
        options = f"  [{s.option_type} ~{s.approx_strike}]" if s.option_type else ""
        print(f"  {s.symbol}: {s.action} @ {s.price:.2f}{levels}{options}  ({', '.join(s.reasons)})")

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
    listener_thread = threading.Thread(target=run_listener, daemon=True)
    listener_thread.start()
    run_loop()
    
