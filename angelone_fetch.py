"""
Fetches OHLCV data for NSE symbols via Angel One's SmartAPI, as a drop-in
alternative to data_fetch.py's yfinance-based fetcher. Keeps the exact same
public shape -- fetch_ohlcv(symbol) -> DataFrame, fetch_all(symbols) -> dict
-- so nothing else in the app (signals.py, backtest.py, telegram_listener.py)
needs to know or care which data source is active. Selected via
DATA_SOURCE="angelone" in config.py.

Unlike yfinance, SmartAPI:
  - has no multi-symbol batch endpoint -- each symbol is a separate,
    rate-limited getCandleData call (3 req/sec, 180 req/min as of this
    writing), so fetching a ~180-symbol watchlist takes a couple of minutes,
    not seconds. Raise POLL_INTERVAL_SECONDS accordingly if you expand the
    watchlist much further.
  - needs a numeric "symboltoken" per symbol, not a plain ticker -- these
    come from Angel's instrument master (a large JSON file), which this
    module downloads once and caches to disk.
  - requires a logged-in session (API key + client code + PIN + TOTP), which
    this module handles automatically and re-establishes if it expires.

Requires a funded Angel One trading account with API access enabled --
see README: "Using Angel One SmartAPI for data" for setup steps.
"""

import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import pyotp
import requests
from SmartApi import SmartConnect

from config import (
    ANGEL_API_KEY,
    ANGEL_CLIENT_CODE,
    ANGEL_INDEX_TOKENS,
    ANGEL_INTERVAL_MAP,
    ANGEL_MAX_DAYS,
    ANGEL_MIN_REQUEST_INTERVAL_SECONDS,
    ANGEL_PIN,
    ANGEL_TOTP_SECRET,
    INTERVAL,
    LOOKBACK_PERIOD,
)

INSTRUMENT_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
_CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTRUMENT_CACHE_PATH = os.path.join(_CACHE_DIR, ".angelone_instruments_cache.json")
_INSTRUMENT_CACHE_MAX_AGE_HOURS = 20  # refresh roughly once a day

_session = {"client": None, "logged_in_at": None}
_token_lookup: dict[str, tuple[str, str]] = {}  # symbol -> (exchange, symboltoken)
_last_request_at = 0.0


def _get_client() -> SmartConnect:
    """Return a logged-in SmartConnect client, logging in (or re-logging in
    once daily, matching SEBI's mandatory daily session reset) as needed."""
    now = datetime.now()
    session_is_stale = (
        _session["client"] is None
        or _session["logged_in_at"] is None
        or (now - _session["logged_in_at"]) > timedelta(hours=8)
    )
    if not session_is_stale:
        return _session["client"]

    if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET]):
        raise RuntimeError(
            "Angel One credentials missing -- set ANGEL_API_KEY, ANGEL_CLIENT_CODE, "
            "ANGEL_PIN, and ANGEL_TOTP_SECRET (see README)."
        )

    client = SmartConnect(ANGEL_API_KEY)
    totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
    data = client.generateSession(ANGEL_CLIENT_CODE, ANGEL_PIN, totp)
    if not data or not data.get("status"):
        raise RuntimeError(f"Angel One login failed: {data}")

    _session["client"] = client
    _session["logged_in_at"] = now
    return client


def _load_instrument_master() -> list[dict]:
    """Download (or load from an on-disk cache) Angel One's full instrument
    master -- a several-MB JSON list of every tradable symbol, used to map
    plain tickers to Angel's numeric symboltoken. Cached to disk since it's
    large and only needs refreshing about once a day."""
    if os.path.exists(_INSTRUMENT_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(_INSTRUMENT_CACHE_PATH)) / 3600
        if age_hours < _INSTRUMENT_CACHE_MAX_AGE_HOURS:
            with open(_INSTRUMENT_CACHE_PATH, "r") as f:
                return json.load(f)

    resp = requests.get(INSTRUMENT_MASTER_URL, timeout=30)
    resp.raise_for_status()
    instruments = resp.json()
    with open(_INSTRUMENT_CACHE_PATH, "w") as f:
        json.dump(instruments, f)
    return instruments


def _build_token_lookup() -> None:
    """Populate _token_lookup for every NSE equity in the instrument master,
    keyed by our app's ".NS"-suffixed ticker style (e.g. "RELIANCE.NS")."""
    global _token_lookup
    if _token_lookup:
        return

    lookup = dict(ANGEL_INDEX_TOKENS)  # indices are hardcoded, not in the master
    instruments = _load_instrument_master()
    for inst in instruments:
        # NSE equities are listed with a "-EQ" suffix, e.g. "RELIANCE-EQ".
        if inst.get("exch_seg") == "NSE" and str(inst.get("symbol", "")).endswith("-EQ"):
            base = inst["symbol"][:-3]  # strip "-EQ"
            lookup[f"{base}.NS"] = ("NSE", inst["token"])

    _token_lookup = lookup


def _resolve_token(symbol: str) -> tuple[str, str]:
    _build_token_lookup()
    if symbol not in _token_lookup:
        raise ValueError(f"Could not resolve Angel One symboltoken for {symbol}")
    return _token_lookup[symbol]


def _rate_limit() -> None:
    """Sleep just enough to stay under Angel One's getCandleData rate limit
    across consecutive calls, regardless of how fast the caller loops."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < ANGEL_MIN_REQUEST_INTERVAL_SECONDS:
        time.sleep(ANGEL_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def _lookback_to_days(period: str) -> int:
    """Parse config.py's yfinance-style LOOKBACK_PERIOD (e.g. "5d") into a
    day count for Angel's fromdate/todate window."""
    period = period.strip().lower()
    if period.endswith("d"):
        return int(period[:-1])
    if period.endswith("mo"):
        return int(period[:-2]) * 30
    if period.endswith("y"):
        return int(period[:-1]) * 365
    raise ValueError(f"Unsupported LOOKBACK_PERIOD for Angel One: {period!r}")


def _parse_candles(raw: list) -> pd.DataFrame:
    """Angel returns rows as [iso_timestamp, open, high, low, close, volume]."""
    if not raw:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(raw, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.set_index("Timestamp")
    df.index.name = None
    return df


def fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch recent OHLCV candles for a single symbol via Angel One SmartAPI."""
    exchange, token = _resolve_token(symbol)
    angel_interval = ANGEL_INTERVAL_MAP.get(INTERVAL)
    if angel_interval is None:
        raise ValueError(f"No Angel One interval mapping for INTERVAL={INTERVAL!r}")

    requested_days = _lookback_to_days(LOOKBACK_PERIOD)
    max_days = ANGEL_MAX_DAYS.get(angel_interval, requested_days)
    days = min(requested_days, max_days)

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    params = {
        "exchange": exchange,
        "symboltoken": token,
        "interval": angel_interval,
        "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
        "todate": to_date.strftime("%Y-%m-%d %H:%M"),
    }

    client = _get_client()
    _rate_limit()
    response = client.getCandleData(params)

    if not response or not response.get("status"):
        raise ValueError(f"Angel One getCandleData failed for {symbol}: {response}")

    df = _parse_candles(response.get("data", []))
    if df.empty:
        raise ValueError(f"No data returned for {symbol} from Angel One.")
    return df


def fetch_all(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for a list of symbols, one rate-limited request at a
    time (Angel One has no batch/multi-symbol endpoint like yfinance does)."""
    data = {}
    for symbol in symbols:
        try:
            data[symbol] = fetch_ohlcv(symbol)
        except Exception as exc:
            print(f"[angelone_fetch] Failed to fetch {symbol}: {exc}")
            continue

    missing = set(symbols) - set(data.keys())
    if missing:
        print(f"[angelone_fetch] No data for {len(missing)} symbols: {sorted(missing)[:10]}"
              f"{'...' if len(missing) > 10 else ''}")

    return data
