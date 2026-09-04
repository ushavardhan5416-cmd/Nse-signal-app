"""
Sends signal alerts to Telegram.

Setup:
1. Message @BotFather on Telegram, run /newbot, and copy the token it gives you.
2. Send any message to your new bot.
3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates in a browser to find
   your chat_id in the JSON response.
4. Put both values into config.py.
"""

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from signals import Signal


def send_telegram_message(text: str) -> None:
    if "PUT_YOUR" in TELEGRAM_BOT_TOKEN or "PUT_YOUR" in TELEGRAM_CHAT_ID:
        print("[notifier] Telegram not configured -- printing instead:\n" + text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[notifier] Failed to send Telegram message: {exc}")


def format_signal(signal: Signal) -> str:
    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[signal.action]
    reasons_text = "\n".join(f"  - {r}" for r in signal.reasons)

    levels = ""
    if signal.target_price is not None and signal.stop_loss is not None:
        reward = abs(signal.target_price - signal.price)
        risk = abs(signal.stop_loss - signal.price)
        rr = reward / risk if risk else 0
        levels = (
            f"🎯 Target: ₹{signal.target_price:.2f}\n"
            f"🛑 Stop-loss: ₹{signal.stop_loss:.2f}\n"
            f"Risk:Reward ≈ 1:{rr:.1f}\n"
        )

    return (
        f"{emoji} *{signal.action}* — {signal.symbol}\n"
        f"Price: ₹{signal.price:.2f}\n"
        f"{levels}"
        f"Time: {signal.timestamp}\n"
        f"Reasons:\n{reasons_text}"
    )


def notify_signals(signals: list[Signal], only_actionable: bool = True) -> None:
    for signal in signals:
        if only_actionable and signal.action == "HOLD":
            continue
        send_telegram_message(format_signal(signal))
       
