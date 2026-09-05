"""
Determines whether "now" falls inside the configured alert window, in IST,
regardless of what timezone the server itself is running in (e.g. Railway
runs in UTC).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    ALERT_END_HOUR,
    ALERT_END_MINUTE,
    ALERT_START_HOUR,
    ALERT_START_MINUTE,
    MARKET_HOLIDAYS,
)

IST = ZoneInfo("Asia/Kolkata")


def is_trading_day(now_ist: datetime) -> bool:
    """Mon-Fri, and not in the (optional) manually-maintained holiday list."""
    if now_ist.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    if now_ist.strftime("%Y-%m-%d") in MARKET_HOLIDAYS:
        return False
    return True


def is_within_alert_window(now: datetime | None = None) -> bool:
    """True if now is a trading day and within the configured hours, in IST --
    converts explicitly so it works correctly regardless of what timezone
    the input (or the server's system clock) is actually in."""
    now_ist = (now or datetime.now(IST)).astimezone(IST)

    if not is_trading_day(now_ist):
        return False

    start_minutes = ALERT_START_HOUR * 60 + ALERT_START_MINUTE
    end_minutes = ALERT_END_HOUR * 60 + ALERT_END_MINUTE
    now_minutes = now_ist.hour * 60 + now_ist.minute

    return start_minutes <= now_minutes <= end_minutes


def now_ist() -> datetime:
    return datetime.now(IST)
