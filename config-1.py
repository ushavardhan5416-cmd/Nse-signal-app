"""
Central configuration for the NSE signals app.
Edit the values below before running.
"""

import os

# --- Watchlist ---
# Symbols are loaded from symbols_fo.txt (one per line, "#" for comments).
# That file covers NSE F&O stocks plus NIFTY/BANKNIFTY/SENSEX indices.
# Edit symbols_fo.txt directly to add/remove names -- see README for how to
# refresh it against NSE's official current F&O list.
def _load_symbols(path: str = "symbols_fo.txt") -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(here, path)
    symbols = []
    with open(full_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols


SYMBOLS = _load_symbols()

# --- Data settings ---
INTERVAL = "15m"      # candle interval: 1m, 5m, 15m, 1h, 1d ...
LOOKBACK_PERIOD = "5d" # how much history to pull each run (yfinance limits intraday history)
BATCH_SIZE = 40        # how many symbols to fetch per yfinance batch call

# --- Data source ---
# "yfinance" (default, free, ~15-20 min delayed) or "angelone" (real SmartAPI
# data via your Angel One account -- much less delayed, needs credentials
# below). Switch back to "yfinance" any time by changing this one value if
# something looks wrong with the Angel One path -- no other code changes
# needed, both sources feed the exact same DataFrame shape downstream.
DATA_SOURCE = os.environ.get("DATA_SOURCE", "yfinance")

# --- Angel One SmartAPI settings (only used when DATA_SOURCE = "angelone") ---
# Get these from smartapi.angelbroking.com (API key) and your Angel One
# trading account (client code, password, TOTP secret from the
# enable-totp page). Set these as environment variables in Railway --
# never commit real credentials into this file.
ANGEL_CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE", "")
ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "")
ANGEL_PASSWORD = os.environ.get("ANGEL_PASSWORD", "")
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "")

# Angel One's official public instrument master -- lists every tradable
# symbol/index with its numeric token, needed to fetch candle data.
ANGEL_INSTRUMENT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

# Angel One's historical-data API has a real rate limit (a handful of
# requests/second). This is a polite delay between each symbol's request
# to avoid getting throttled/blocked -- increase if you still hit limits.
ANGEL_REQUEST_DELAY_SECONDS = 0.35

# Maps our internal interval string to Angel One's expected interval name.
ANGEL_INTERVAL_MAP = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "1d": "ONE_DAY",
}

# Angel One index symbols aren't in the regular equity instrument list --
# these are well-known fixed tokens on the NSE/BSE index segment. Maps our
# existing yfinance-style index tickers to Angel One's (exchange, token,
# name) triple. Verify against Angel One's own docs/instrument master if a
# fetch for one of these ever fails -- index tokens are stable but not
# guaranteed unchanging.
ANGEL_INDEX_TOKENS = {
    "^NSEI": ("NSE", "99926000", "NIFTY"),
    "^NSEBANK": ("NSE", "99926009", "BANKNIFTY"),
    "^CNXFIN": ("NSE", "99926037", "FINNIFTY"),
    "^BSESN": ("BSE", "99919000", "SENSEX"),
    "^CRSMID": ("NSE", "99926074", "MIDCPNIFTY"),
}

# --- Indicator settings ---
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

SMA_SHORT = 20
SMA_LONG = 50

# --- Target / stop-loss settings ---
# Targets and stops are sized off ATR (Average True Range) so they scale with
# each stock's actual volatility, rather than using a fixed percentage that
# would be too tight for volatile stocks and too loose for stable ones.
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5    # stop-loss = entry price -/+ (ATR * this)
ATR_TARGET_MULTIPLIER = 2.5  # target = entry price +/- (ATR * this)
# Risk:reward with these defaults is 1 : 1.67

# --- Chart pattern (breakout) settings ---
# A bullish breakout = close above the highest high of the prior N candles.
# A bearish breakout = close below the lowest low of the prior N candles.
BREAKOUT_LOOKBACK = 20

# --- Trend strength gate (ADX) ---
# ADX measures how strongly a trend is developing, regardless of direction.
# Signals are suppressed (forced to HOLD) when ADX is below this threshold,
# even if RSI/MACD/SMA/breakout would otherwise agree -- this is meant to
# cut down whipsaw signals in flat/choppy markets. 25 is the standard
# textbook threshold for "a trend is underway"; lower it to catch more
# (weaker) trends, raise it to be more selective.
ADX_PERIOD = 14
ADX_THRESHOLD = 25

# --- Volume confirmation ---
# A breakout only counts toward the vote if volume is meaningfully above its
# recent average -- a breakout on weak volume is much less reliable. This is
# automatically skipped for symbols with no real volume data (indices report
# 0 volume via yfinance), so it only applies to individual stocks.
VOLUME_MA_PERIOD = 20
VOLUME_CONFIRMATION_MULTIPLIER = 1.5

# --- Chart pattern detection (candlestick + reversal patterns) ---
# These feed the 5th vote condition, alongside RSI/MACD/SMA/breakout.
# PATTERN_LOOKBACK: how many recent candles to scan for double top/bottom
# and head & shoulders formations.
PATTERN_LOOKBACK = 40
# PEAK_ORDER: a candle counts as a local peak/trough if it's the highest/
# lowest point within this many candles on each side.
PEAK_ORDER = 3
# How close two peaks/troughs must be (as a fraction of price) to count as
# "similar height" for a double top/bottom or head & shoulders shoulders.
PATTERN_SIMILARITY_TOLERANCE = 0.02  # 2%
# Minimum depth of the trough between two peaks (as a fraction of price) for
# a double top to count as a real reversal pattern, not just noise. Mirrored
# for double bottom (minimum height of the peak between two troughs).
PATTERN_MIN_DEPTH = 0.015  # 1.5%

# --- Options (CE/PE) settings ---
# Strike price interval used to round the underlying's price to an
# approximate ATM (at-the-money) strike for the options suggestion. Known
# indices have fixed intervals; anything else falls back to a rough
# price-based heuristic in signals.py (see round_to_strike()).
STRIKE_INTERVALS = {
    "^NSEI": 50,      # Nifty 50
    "^NSEBANK": 100,  # Bank Nifty
    "^BSESN": 100,    # Sensex
    "^CNXFIN": 50,    # Fin Nifty
}

# --- Alerting ---
# Create a bot via @BotFather on Telegram, then message it once and fetch your
# chat_id via https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PUT_YOUR_TELEGRAM_CHAT_ID_HERE")

# How often (seconds) to poll Telegram for incoming on-demand queries (e.g.
# sending "RELIANCE" to the bot to check its current signal right now).
# This runs independently of, and much more often than, the main scheduled
# alert cycle below.
TELEGRAM_POLL_INTERVAL_SECONDS = 3

# --- Run mode ---
# How often (seconds) the polling loop re-checks the market in `main.py`.
POLL_INTERVAL_SECONDS = 900  # 15 minutes, matches INTERVAL by default

# --- Alert window ---
# Alerts (and the fetch/signal cycle itself) only run within this window, on
# trading days (Mon-Fri). Times are in IST regardless of what timezone the
# server itself runs in (e.g. Railway runs in UTC).
ALERT_START_HOUR = 8
ALERT_START_MINUTE = 30
ALERT_END_HOUR = 17
ALERT_END_MINUTE = 0

# NSE market holidays are NOT accounted for automatically -- add dates here
# (YYYY-MM-DD strings) for known holidays if you want the app to skip them too.
MARKET_HOLIDAYS: list[str] = []

# --- Daily summary ---
# Time (IST) to send the daily target/stop-loss summary. Must fall within
# the alert window above for it to actually get checked/sent.
SUMMARY_HOUR = 15
SUMMARY_MINUTE = 30

# --- Risk management ---
# These cap how many new positions the app opens per day, regardless of how
# many signals fire. Inspired by a similar layer in a comparable paper-trading
# app: capping trade frequency and concurrent exposure is a basic discipline
# control, even though this app doesn't manage real capital.
MAX_TRADES_PER_DAY = 5       # new positions opened per day, across all symbols
MAX_OPEN_POSITIONS = 3       # concurrent open positions, across all symbols

# Daily loss limit is expressed as a % of an ASSUMED notional capital per
# trade -- since this app doesn't buy real option premiums, there's no real
# P&L to track. This is a proxy: it estimates P&L as if each trade risked
# ASSUMED_CAPITAL_PER_TRADE rupees, sized by the underlying's actual %
# move between entry and exit. Once the day's estimated loss crosses this
# limit, no new positions are opened until the next trading day. Purely
# illustrative -- adjust or ignore if you're not using it to size real trades.
ASSUMED_CAPITAL_PER_TRADE = 15000.0
DAILY_LOSS_LIMIT_PCT = 3.0   # % of ASSUMED_CAPITAL_PER_TRADE
