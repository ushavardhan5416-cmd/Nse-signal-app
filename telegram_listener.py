"""
Polls Telegram for incoming messages so you can ask about any stock/index on
demand, instead of only receiving scheduled alerts. Runs in a background
thread alongside the main polling loop in main.py.

Usage (send any of these to your bot in Telegram):
  RELIANCE            -> current signal for RELIANCE.NS
  /check TCS          -> same, "/check " prefix is optional
  NIFTY / BANKNIFTY / SENSEX  -> index shortcuts
  /help               -> usage info

Only messages from TELEGRAM_CHAT_ID are processed -- this keeps random
strangers from being able to spam the bot into hammering yfinance, since
anyone who finds the bot's username could otherwise message it freely.
"""

import time

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_POLL_INTERVAL_SECONDS
from data_fetch import fetch_ohlcv
from notifier import format_signal, send_telegram_message
from signals import generate_signal

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

INDEX_ALIASES = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
}

HELP_TEXT = (
    "Send me a stock or index name and I'll check its current signal.\n\n"
    "Examples:\n"
    "  RELIANCE\n"
    "  /check TCS\n"
    "  NIFTY / BANKNIFTY / SENSEX\n"
)


def resolve_symbol(raw: str) -> str:
    """Turn user input like 'reliance', '/check TCS', or 'nifty' into a
    yfinance-compatible ticker."""
    text = raw.strip().upper()
    if text.startswith("/CHECK"):
        text = text[len("/CHECK"):].strip()
    text = text.lstrip("/").strip()

    if text in INDEX_ALIASES:
        return INDEX_ALIASES[text]
    if text.startswith("^") or text.endswith(".NS"):
        return text
    return f"{text}.NS"


def handle_command(text: str) -> str:
    """Process one incoming message and return the reply text."""
    stripped = text.strip()
    upper = stripped.upper()

    if upper in ("/HELP", "HELP", "/START"):
        return HELP_TEXT

    symbol = resolve_symbol(stripped)

    try:
        df = fetch_ohlcv(symbol)
    except Exception as exc:
        return f"Couldn't fetch data for {symbol}: {exc}"

    try:
        signal = generate_signal(symbol, df)
    except Exception as exc:
        return f"Couldn't compute a signal for {symbol}: {exc}"

    return format_signal(signal)


def _get_updates(offset: int | None) -> list:
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", [])


def _skip_backlog() -> int | None:
    """On startup, discard any messages sent while the app wasn't running
    (e.g. during a redeploy), so it doesn't reply to a pile of stale
    messages all at once. Returns the offset to start listening from."""
    try:
        updates = _get_updates(offset=None)
    except Exception as exc:
        print(f"[telegram_listener] Couldn't check for backlog: {exc}")
        return None
    if not updates:
        return None
    return updates[-1]["update_id"] + 1


def run_listener() -> None:
    if "PUT_YOUR" in TELEGRAM_BOT_TOKEN or "PUT_YOUR" in TELEGRAM_CHAT_ID:
        print("[telegram_listener] Telegram not configured -- on-demand queries disabled.")
        return

    print("[telegram_listener] Listening for on-demand queries...")
    offset = _skip_backlog()

    while True:
        try:
            updates = _get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "")

                if not text or chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                reply = handle_command(text)
                send_telegram_message(reply)
        except Exception as exc:
            print(f"[telegram_listener] Error: {exc}")

        time.sleep(TELEGRAM_POLL_INTERVAL_SECONDS)
