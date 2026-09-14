"""
Angel One SmartAPI data client -- an alternative to yfinance with much less
delay, using your own Angel One trading account (read-only market data; this
module never places, modifies, or cancels an order).

Used when DATA_SOURCE = "angelone" in config.py. Returns data in the exact
same shape as data_fetch.py's yfinance path (a DataFrame per symbol with
Open/High/Low/Close/Volume columns), so nothing downstream (indicators,
signals, notifier, position_tracker) needs to know which source is active.

Setup: needs smartapi-python and pyotp installed (see requirements.txt), and
ANGEL_CLIENT_CODE / ANGEL_API_KEY / ANGEL_PASSWORD / ANGEL_TOTP_SECRET set as
environment variables (see README for how to get these).
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import (
    ANGEL_API_KEY,
    ANGEL_CLIENT_CODE,
    ANGEL_INDEX_TOKENS,
    ANGEL_INSTRUMENT_MASTER_URL,
    ANGEL_INTERVAL_MAP,
    ANGEL_PASSWORD,
    ANGEL_REQUEST_DELAY_SECONDS,
    ANGEL_TOTP_SECRET,
    INTERVAL,
)
from market_hours import now_ist

# Module-level caches so we don't re-login or re-download the (large)
# instrument master on every single symbol -- both are reused for the
# lifetime of the running process, refreshed only if a session expires.
_session = None
_session_client = None
_instrument_master_df = None


def _require_credentials() -> None:
    missing = [
        name
        for name, value in [
            ("ANGEL_CLIENT_CODE", ANGEL_CLIENT_CODE),
            ("ANGEL_API_KEY", ANGEL_API_KEY),
            ("ANGEL_PASSWORD", ANGEL_PASSWORD),
            ("ANGEL_TOTP_SECRET", ANGEL_TOTP_SECRET),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            f"DATA_SOURCE is 'angelone' but these env vars are missing: {', '.join(missing)}. "
            f"Set them in Railway's Variables tab, or switch DATA_SOURCE back to 'yfinance'."
        )


def _login():
    """Logs in via TOTP and returns an authenticated SmartConnect client.
    Cached at module level -- reused across calls until it errors, at which
    point the caller should clear _session_client and retry once."""
    global _session, _session_client

    if _session_client is not None:
        return _session_client

    _require_credentials()

    # Imported lazily so the app can still start up fine with DATA_SOURCE =
    # "yfinance" even if smartapi-python/pyotp aren't installed yet.
    import pyotp
    from SmartApi import SmartConnect

    client = SmartConnect(api_key=ANGEL_API_KEY)
    totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
    session = client.generateSession(ANGEL_CLIENT_CODE, ANGEL_PASSWORD, totp)

    if not session or session.get("status") is False:
        raise RuntimeError(f"Angel One SmartAPI login failed: {session}")

    _session = session
    _session_client = client
    return client


def _reset_session() -> None:
    """Forces the next _login() call to re-authenticate from scratch."""
    global _session, _session_client
    _session = None
    _session_client = None


def _load_instrument_master() -> pd.DataFrame:
    """Downloads and caches Angel One's full instrument list. Large file
    (~tens of MB) -- fetched once per process lifetime, not per symbol."""
    global _instrument_master_df

    if _instrument_master_df is not None:
        return _instrument_master_df

    response = requests.get(ANGEL_INSTRUMENT_MASTER_URL, timeout=60)
    response.raise_for_status()
    df = pd.DataFrame(response.json())

    for col in ("exch_seg", "name", "symbol"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper()

    _instrument_master_df = df
    return df


def resolve_symbol(symbol: str) -> tuple[str, str]:
    """Resolves one of our internal symbols (e.g. 'RELIANCE.NS', '^NSEI')
    into an Angel One (exchange, token) pair.

    Indices use the fixed lookup table in config.py (ANGEL_INDEX_TOKENS) --
    more reliable than searching the instrument master, since index entries
    there are sparse/inconsistent. Stocks are resolved dynamically against
    the instrument master by matching the NSE cash-equity ("-EQ") listing,
    so this keeps working even if a stock's actual token changes over time.
    """
    if symbol in ANGEL_INDEX_TOKENS:
        exchange, token, _name = ANGEL_INDEX_TOKENS[symbol]
        return exchange, token

    if not symbol.endswith(".NS"):
        raise ValueError(f"Don't know how to resolve symbol for Angel One: {symbol}")

    root = symbol[: -len(".NS")].upper()
    master = _load_instrument_master()

    matches = master[
        (master["exch_seg"] == "NSE")
        & (master["name"] == root)
        & (master["symbol"].str.endswith("-EQ"))
    ]
    if matches.empty:
        raise ValueError(f"No NSE cash-equity listing found for '{root}' in the instrument master")

    return "NSE", str(matches.iloc[0]["token"])


def _parse_candle_rows(rows: list) -> pd.DataFrame:
    """Converts Angel One's raw candle rows (list of
    [timestamp, open, high, low, close, volume]) into our standard
    OHLCV DataFrame shape, matching what the yfinance path produces."""
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df.index.name = None
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_ohlcv_angelone(symbol: str, lookback_days: int = 5) -> pd.DataFrame:
    """Fetches recent OHLCV candles for a single symbol via Angel One
    SmartAPI. Raises on failure rather than silently returning empty data,
    matching the yfinance path's fetch_ohlcv() behavior."""
    client = _login()
    exchange, token = resolve_symbol(symbol)

    angel_interval = ANGEL_INTERVAL_MAP.get(INTERVAL)
    if angel_interval is None:
        raise ValueError(f"No Angel One interval mapping for INTERVAL='{INTERVAL}' -- add one to ANGEL_INTERVAL_MAP")

    to_dt = now_ist()
    from_dt = to_dt - timedelta(days=lookback_days)
    params = {
        "exchange": exchange,
        "symboltoken": token,
        "interval": angel_interval,
        "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
    }

    try:
        response = client.getCandleData(params)
    except Exception as exc:
        # A stale/expired session is a common cause of a sudden failure --
        # retry once with a fresh login before giving up on this symbol.
        _reset_session()
        client = _login()
        response = client.getCandleData(params)
        if not response:
            raise RuntimeError(f"Angel One candle fetch failed for {symbol}: {exc}") from exc

    if not response or response.get("status") is False:
        raise RuntimeError(f"Angel One candle fetch failed for {symbol}: {response}")

    rows = response.get("data") or []
    df = _parse_candle_rows(rows)
    if df.empty:
        raise ValueError(f"No candle data returned for {symbol}")

    return df


def fetch_all_angelone(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetches OHLCV data for a list of symbols via Angel One SmartAPI,
    matching data_fetch.fetch_all()'s return shape exactly. Angel One's
    historical API doesn't support true batch requests the way yfinance
    does, so this fetches one symbol at a time with a polite delay between
    calls to stay within rate limits."""
    data = {}

    for symbol in symbols:
        try:
            data[symbol] = fetch_ohlcv_angelone(symbol)
        except Exception as exc:
            print(f"[angel_client] Skipping {symbol}: {exc}")
        time.sleep(ANGEL_REQUEST_DELAY_SECONDS)

    missing = set(symbols) - set(data.keys())
    if missing:
        print(f"[angel_client] No data for {len(missing)} symbols: {sorted(missing)[:10]}"
              f"{'...' if len(missing) > 10 else ''}")

    return data
