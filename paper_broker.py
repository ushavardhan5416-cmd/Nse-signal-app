"""
Simulates placing and managing option orders (CE/PE, buying only) using
REAL premiums fetched from Angel One -- this is paper trading: no real
order is ever sent to the exchange. Controlled by config.PAPER_TRADING,
which should stay True until you've watched this run and trust it.

Mirrors the day-rollover-reset design from the earlier position_tracker.py:
daily counters reset at the first cycle of a new calendar day, not tied to
whether a summary successfully fired -- this matters because a crash or
redeploy before day-end would otherwise carry stale counts into the next
day and wrongly block trading via the daily limits below.
"""

from datetime import date, datetime

from config import (
    CAPITAL,
    DAILY_LOSS_LIMIT,
    FORCE_EXIT_HOUR,
    FORCE_EXIT_MINUTE,
    LOT_SIZES,
    MAX_LOTS_PER_TRADE,
    MAX_OPEN_POSITIONS,
    MAX_TRADES_PER_DAY,
    PAPER_TRADING,
    PREMIUM_STOP_PCT,
    PREMIUM_TARGET_PCT,
    RISK_PER_TRADE,
    SUMMARY_HOUR,
    SUMMARY_MINUTE,
)
from notifier import send_telegram_message
from option_chain import fetch_option_ltp, resolve_option_contract

# symbol -> dict(contract, option_type, entry_premium, lots, lot_size,
#                 target_premium, stop_premium, opened_at)
_open_positions: dict[str, dict] = {}

_daily_trades_opened = 0
_daily_wins = 0
_daily_losses = 0
_daily_pnl = 0.0
_daily_limit_hit_notified = False
_current_date: date | None = None
_last_summary_date: date | None = None


def _ensure_day(now: datetime) -> None:
    global _daily_trades_opened, _daily_wins, _daily_losses
    global _daily_pnl, _daily_limit_hit_notified, _current_date

    today = now.date()
    if _current_date == today:
        return

    _daily_trades_opened = 0
    _daily_wins = 0
    _daily_losses = 0
    _daily_pnl = 0.0
    _daily_limit_hit_notified = False
    _current_date = today


def _risk_check_reason() -> str | None:
    if _daily_trades_opened >= MAX_TRADES_PER_DAY:
        return f"max trades/day reached ({MAX_TRADES_PER_DAY})"
    if len(_open_positions) >= MAX_OPEN_POSITIONS:
        return f"max open positions reached ({MAX_OPEN_POSITIONS})"
    if _daily_pnl <= -DAILY_LOSS_LIMIT:
        return f"daily loss limit reached (₹{-_daily_pnl:.0f})"
    return None


def _position_size(entry_premium: float, lot_size: int) -> int | None:
    """Sizes the trade so a full stop-loss hit loses roughly RISK_PER_TRADE
    rupees, capped at MAX_LOTS_PER_TRADE regardless. Returns None if even 1
    lot's risk meaningfully exceeds RISK_PER_TRADE -- silently taking a
    trade at several times the intended risk budget (which happens easily
    at realistic premium levels, e.g. a 150-premium Nifty option already
    risks ~₹1,460/lot against a ₹500 budget) would break the entire point
    of having a risk-managed system, so this is a hard skip, not a floor."""
    stop_amount_per_lot = entry_premium * (PREMIUM_STOP_PCT / 100) * lot_size
    if stop_amount_per_lot <= 0:
        return 1
    if stop_amount_per_lot > RISK_PER_TRADE * 1.5:
        return None
    lots = max(1, int(RISK_PER_TRADE // stop_amount_per_lot))
    return min(lots, MAX_LOTS_PER_TRADE)


def is_paper_trading() -> bool:
    return PAPER_TRADING


def place_paper_order(symbol: str, option_type: str, spot_price: float, now: datetime) -> None:
    """Attempts to open a new paper position, subject to risk limits and
    not already having one open on this symbol."""
    global _daily_trades_opened, _daily_limit_hit_notified

    _ensure_day(now)

    if symbol in _open_positions:
        return  # already tracking a move on this symbol

    block_reason = _risk_check_reason()
    if block_reason:
        if not _daily_limit_hit_notified:
            send_telegram_message(
                f"⏸ *Paper trading paused* -- no new trades today ({block_reason})."
            )
            _daily_limit_hit_notified = True
        return

    contract = resolve_option_contract(symbol, option_type, spot_price)
    entry_premium = fetch_option_ltp(contract)
    lot_size = contract["lot_size"] or LOT_SIZES.get(symbol, 1)
    lots = _position_size(entry_premium, lot_size)

    if lots is None:
        risk_per_lot = entry_premium * (PREMIUM_STOP_PCT / 100) * lot_size
        send_telegram_message(
            f"⚠️ Skipped {option_type} {contract['tradingsymbol']}: even 1 lot's stop-loss risk "
            f"(₹{risk_per_lot:.0f}) is too large for the ₹{RISK_PER_TRADE:.0f} risk budget. "
            f"Raise RISK_PER_TRADE in config.py if this should still be taken."
        )
        return

    target_premium = entry_premium * (1 + PREMIUM_TARGET_PCT / 100)
    stop_premium = entry_premium * (1 - PREMIUM_STOP_PCT / 100)

    _open_positions[symbol] = {
        "contract": contract,
        "option_type": option_type,
        "entry_premium": entry_premium,
        "lots": lots,
        "lot_size": lot_size,
        "target_premium": target_premium,
        "stop_premium": stop_premium,
        "opened_at": now,
    }
    _daily_trades_opened += 1

    tag = "[PAPER]" if PAPER_TRADING else "[LIVE]"
    send_telegram_message(
        f"🟢 {tag} *BUY {option_type}* — {contract['tradingsymbol']}\n"
        f"Entry premium: ₹{entry_premium:.2f} × {lots} lot(s) × {lot_size} qty\n"
        f"🎯 Target: ₹{target_premium:.2f}   🛑 Stop: ₹{stop_premium:.2f}\n"
        f"Expiry: {contract['expiry']}"
    )


def check_paper_positions(now: datetime) -> None:
    """Checks every open paper position's real current premium against its
    target/stop, and force-exits anything still open past FORCE_EXIT_HOUR."""
    global _daily_wins, _daily_losses, _daily_pnl

    _ensure_day(now)

    force_exit_now = (now.hour, now.minute) >= (FORCE_EXIT_HOUR, FORCE_EXIT_MINUTE)

    for symbol in list(_open_positions.keys()):
        position = _open_positions[symbol]
        try:
            current_premium = fetch_option_ltp(position["contract"])
        except Exception as exc:
            print(f"[paper_broker] Couldn't fetch LTP for {symbol}, will retry next cycle: {exc}")
            continue

        hit = None
        if current_premium >= position["target_premium"]:
            hit = "TARGET"
        elif current_premium <= position["stop_premium"]:
            hit = "STOP"
        elif force_exit_now:
            hit = "FORCE_EXIT"

        if hit is None:
            continue

        entry = position["entry_premium"]
        pnl = (current_premium - entry) * position["lots"] * position["lot_size"]
        _daily_pnl += pnl

        tag = "[PAPER]" if PAPER_TRADING else "[LIVE]"
        contract = position["contract"]

        if hit == "TARGET":
            _daily_wins += 1
            send_telegram_message(
                f"✅ {tag} *TARGET HIT* — {contract['tradingsymbol']}\n"
                f"Entry: ₹{entry:.2f} → Exit: ₹{current_premium:.2f}\n"
                f"P&L: +₹{pnl:.0f}"
            )
        elif hit == "STOP":
            _daily_losses += 1
            send_telegram_message(
                f"🛑 {tag} *STOP HIT* — {contract['tradingsymbol']}\n"
                f"Entry: ₹{entry:.2f} → Exit: ₹{current_premium:.2f}\n"
                f"P&L: ₹{pnl:.0f}"
            )
        else:  # FORCE_EXIT
            if pnl >= 0:
                _daily_wins += 1
            else:
                _daily_losses += 1
            send_telegram_message(
                f"⏰ {tag} *FORCE EXIT* (end of day) — {contract['tradingsymbol']}\n"
                f"Entry: ₹{entry:.2f} → Exit: ₹{current_premium:.2f}\n"
                f"P&L: ₹{pnl:.0f}"
            )

        del _open_positions[symbol]


def maybe_send_paper_summary(now: datetime) -> None:
    """Sends a once-per-day paper-trading summary once `now` (IST) reaches
    SUMMARY_HOUR/SUMMARY_MINUTE -- same config values and same once-per-day
    pattern as position_tracker.py's summary, so you get one combined sense
    of "what happened today" rather than two separately-timed messages."""
    global _last_summary_date

    _ensure_day(now)

    today = now.date()
    if _last_summary_date == today:
        return  # already sent today

    if (now.hour, now.minute) < (SUMMARY_HOUR, SUMMARY_MINUTE):
        return  # not time yet

    total = _daily_wins + _daily_losses
    if total == 0:
        message = (
            f"📊 *Paper Trading Summary* — {today}\n"
            f"No trades closed today. Opened: {_daily_trades_opened}"
        )
    else:
        win_rate = _daily_wins / total * 100
        message = (
            f"📊 *Paper Trading Summary* — {today}\n"
            f"✅ Wins: {_daily_wins}   🛑 Losses: {_daily_losses}\n"
            f"Win rate: {win_rate:.0f}%\n"
            f"Trades opened: {_daily_trades_opened}\n"
            f"Net P&L: ₹{_daily_pnl:.0f}"
        )

    send_telegram_message(message)
    _last_summary_date = today


def _reset_for_testing() -> None:
    global _daily_trades_opened, _daily_wins, _daily_losses
    global _daily_pnl, _daily_limit_hit_notified, _current_date, _last_summary_date
    _open_positions.clear()
    _daily_trades_opened = 0
    _daily_wins = 0
    _daily_losses = 0
    _daily_pnl = 0.0
    _daily_limit_hit_notified = False
    _current_date = None
    _last_summary_date = None
