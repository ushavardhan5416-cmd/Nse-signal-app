"""
Resolves the actual tradable option contract (strike, expiry, token) for
Nifty, Bank Nifty, and Sensex, and fetches its real current premium (LTP)
via Angel One SmartAPI.

This is the highest-stakes module in the auto-trading path: a wrong strike
or expiry resolution means trading (even in paper mode) the wrong contract
entirely. Everything here fails loudly (raises) rather than silently
falling back to a guess, on the principle that a clear error is far safer
than a wrong trade.

Known assumption to verify on first live run: Angel One's instrument master
stores each option's strike price scaled by 100 (e.g. a 24500 strike is
stored as 2450000) -- this is Angel One's documented convention, but hasn't
been verified against live data from this environment (no network access
to Angel One's servers here). _parse_strike() below flags clearly in its
docstring and via a sanity-range check if a value looks implausible.
"""

from datetime import datetime, timedelta

import pandas as pd

from angel_client import _load_instrument_master, _login
from config import LOT_SIZES, OPTION_EXCHANGE_SEGMENT, OPTION_UNDERLYING_NAME, STRIKE_INTERVALS


def round_to_strike(symbol: str, price: float) -> int:
    """Round the underlying's price to the nearest real strike interval."""
    interval = STRIKE_INTERVALS.get(symbol, 100)
    return round(price / interval) * interval


def _parse_strike(raw_strike) -> float:
    """Angel One stores strike prices scaled by 100 (e.g. 2450000 for a
    24500 strike) -- documented SmartAPI convention. A plausibility check
    guards against that assumption being wrong: real index strikes fall
    roughly in the 100-100,000 range after scaling down; if the scaled-down
    value looks wildly implausible, raise rather than silently using a bad
    strike."""
    value = float(raw_strike) / 100.0
    if not (100 <= value <= 150000):
        raise ValueError(
            f"Parsed strike {value} from raw value {raw_strike} looks implausible -- "
            f"Angel One's strike-scaling convention may have changed. Verify against "
            f"a live instrument master entry before trusting this."
        )
    return value


def _parse_expiry(raw_expiry: str) -> datetime:
    """Angel One's instrument master formats expiry as e.g. '25SEP2025' or
    '25-SEP-2025' depending on the field. Tries a few common formats."""
    raw = str(raw_expiry).strip().upper().replace("-", "")
    for fmt in ("%d%b%Y", "%d%B%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Couldn't parse expiry date '{raw_expiry}' with any known format")


def get_option_chain(symbol: str) -> pd.DataFrame:
    """Returns all CE/PE option instruments for this underlying's nearest
    (current) expiry, across all available strikes."""
    if symbol not in OPTION_UNDERLYING_NAME:
        raise ValueError(f"{symbol} is not in scope for options trading (config.TRADE_SYMBOLS)")

    underlying_name = OPTION_UNDERLYING_NAME[symbol]
    exchange_segment = OPTION_EXCHANGE_SEGMENT[symbol]

    master = _load_instrument_master()
    candidates = master[
        (master["exch_seg"] == exchange_segment)
        & (master["name"] == underlying_name)
        & (master["instrumenttype"] == "OPTIDX")
    ].copy()

    if candidates.empty:
        raise ValueError(
            f"No {underlying_name} options found on {exchange_segment} in the instrument "
            f"master -- check OPTION_UNDERLYING_NAME/OPTION_EXCHANGE_SEGMENT in config.py"
        )

    candidates["expiry_date"] = candidates["expiry"].apply(_parse_expiry)

    today = datetime.now().date()
    upcoming = candidates[candidates["expiry_date"].dt.date >= today]
    if upcoming.empty:
        raise ValueError(f"No upcoming {underlying_name} option expiries found -- instrument master may be stale")

    nearest_expiry = upcoming["expiry_date"].min()
    chain = upcoming[upcoming["expiry_date"] == nearest_expiry].copy()
    chain["strike_price"] = chain["strike"].apply(_parse_strike)

    return chain


def resolve_option_contract(symbol: str, option_type: str, spot_price: float) -> dict:
    """Resolves the ATM (at-the-money) option contract closest to the
    current spot price. Returns a dict with everything needed to fetch a
    quote or place an order: token, exchange, tradingsymbol, strike,
    expiry, lot_size."""
    if option_type not in ("CE", "PE"):
        raise ValueError(f"option_type must be 'CE' or 'PE', got {option_type!r}")

    chain = get_option_chain(symbol)
    target_strike = round_to_strike(symbol, spot_price)

    same_type = chain[chain["symbol"].str.endswith(option_type)]
    if same_type.empty:
        raise ValueError(f"No {option_type} contracts found in the {symbol} option chain")

    same_type = same_type.copy()
    same_type["strike_distance"] = (same_type["strike_price"] - target_strike).abs()
    best = same_type.sort_values("strike_distance").iloc[0]

    return {
        "token": str(best["token"]),
        "exchange": OPTION_EXCHANGE_SEGMENT[symbol],
        "tradingsymbol": str(best["symbol"]),
        "strike": float(best["strike_price"]),
        "expiry": best["expiry_date"].strftime("%Y-%m-%d"),
        "lot_size": LOT_SIZES.get(symbol),
    }


def fetch_option_ltp(contract: dict) -> float:
    """Fetches the real current last-traded price (premium) for a resolved
    option contract."""
    client = _login()
    response = client.ltpData(contract["exchange"], contract["tradingsymbol"], contract["token"])

    if not response or response.get("status") is False:
        raise RuntimeError(f"LTP fetch failed for {contract['tradingsymbol']}: {response}")

    ltp = response.get("data", {}).get("ltp")
    if ltp is None or ltp <= 0:
        raise ValueError(f"Invalid LTP returned for {contract['tradingsymbol']}: {ltp}")

    return float(ltp)
