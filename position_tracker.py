"""
Tracks open BUY/SELL positions (opened when a signal actually fires) so the
app can:
1. Notify you when a position's target or stop-loss is hit.
2. Send a daily summary of targets hit vs stop-losses hit, at a configured
   time (see SUMMARY_HOUR/SUMMARY_MINUTE in config.py).

State lives in memory for the lifetime of the running process -- it resets
if the app restarts or redeploys (e.g. after a Railway redeploy mid-day).
This is a lightweight tracker for the app's own alerts, NOT a substitute
for checking your actual broker positions.
"""

from datetime import date, datetime

from config import SUMMARY_HOUR, SUMMARY_MINUTE
from notifier import send_telegram_message
from signals import Signal

# symbol -> dict(action, entry_price, target_price, stop_loss, option_type,
#                 approx_strike, opened_at)
_open_positions: dict[str, dict] = {}

_daily_target_hits = 0
_daily_stop_hits = 0
_last_summary_date: date | None = None


def open_position(signal: Signal) -> None:
    """Start tracking a newly confirmed BUY/SELL signal, if not already
    tracking that symbol (avoids duplicate/overlapping positions on the
    same symbol while a move is still playing out)."""
    if not signal.is_actionable:
        return
    if signal.target_price is None or signal.stop_loss is None:
        return
    if signal.symbol in _open_positions:
        return

    _open_positions[signal.symbol] = {
        "action": signal.action,
        "entry_price": signal.price,
        "target_price": signal.target_price,
        "stop_loss": signal.stop_loss,
        "option_type": signal.option_type,
        "approx_strike": signal.approx_strike,
        "opened_at": signal.timestamp,
    }


def check_positions(latest_signals: list[Signal]) -> None:
    """Check every open position against this cycle's freshly fetched
    price; notify and close out any that have hit target or stop-loss."""
    global _daily_target_hits, _daily_stop_hits

    latest_by_symbol = {s.symbol: s for s in latest_signals}

    for symbol in list(_open_positions.keys()):
        position = _open_positions[symbol]
        current = latest_by_symbol.get(symbol)
        if current is None:
            continue  # no fresh price for this symbol this cycle -- check again next time

        price = current.price
        hit = None

        if position["action"] == "BUY":
            if price >= position["target_price"]:
                hit = "TARGET"
            elif price <= position["stop_loss"]:
                hit = "STOP"
        elif position["action"] == "SELL":
            if price <= position["target_price"]:
                hit = "TARGET"
            elif price >= position["stop_loss"]:
                hit = "STOP"

        if hit == "TARGET":
            _daily_target_hits += 1
            send_telegram_message(
                f"✅ *TARGET HIT* — {symbol}\n"
                f"{position['action']} entry: ₹{position['entry_price']:.2f}\n"
                f"Now: ₹{price:.2f}\n"
                f"Target was: ₹{position['target_price']:.2f}"
            )
            del _open_positions[symbol]
        elif hit == "STOP":
            _daily_stop_hits += 1
            send_telegram_message(
                f"🛑 *STOP-LOSS HIT* — {symbol}\n"
                f"{position['action']} entry: ₹{position['entry_price']:.2f}\n"
                f"Now: ₹{price:.2f}\n"
                f"Stop was: ₹{position['stop_loss']:.2f}"
            )
            del _open_positions[symbol]


def maybe_send_daily_summary(now: datetime) -> None:
    """Send a once-per-day summary once `now` (IST) reaches the configured
    summary time, then reset the counters for the next day."""
    global _daily_target_hits, _daily_stop_hits, _last_summary_date

    today = now.date()
    if _last_summary_date == today:
        return  # already sent today

    minutes_now = now.hour * 60 + now.minute
    minutes_target = SUMMARY_HOUR * 60 + SUMMARY_MINUTE
    if minutes_now < minutes_target:
        return  # not time yet

    total = _daily_target_hits + _daily_stop_hits
    if total:
        win_rate = _daily_target_hits / total * 100
        message = (
            f"📊 *Daily Summary* — {today}\n"
            f"✅ Targets hit: {_daily_target_hits}\n"
            f"🛑 Stop-losses hit: {_daily_stop_hits}\n"
            f"Win rate: {win_rate:.0f}%"
        )
    else:
        message = f"📊 *Daily Summary* — {today}\nNo positions closed today."

    send_telegram_message(message)

    _daily_target_hits = 0
    _daily_stop_hits = 0
    _last_summary_date = today


def _reset_for_testing() -> None:
    """Test-only helper to reset module state between test cases."""
    global _daily_target_hits, _daily_stop_hits, _last_summary_date
    _open_positions.clear()
    _daily_target_hits = 0
    _daily_stop_hits = 0
    _last_summary_date = None
