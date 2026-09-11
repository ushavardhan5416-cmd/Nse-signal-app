"""
Central configuration for the NSE signals app.
Edit the values below before running.
"""

import os

# --- Data source ---
# "yfinance" (default -- free, delayed, no account needed, works out of the
# box) or "angelone" (Angel One SmartAPI -- real-time-ish data, but needs a
# funded Angel One trading account with API access enabled). See README:
# "Using Angel One SmartAPI for data" for setup.
DATA_SOURCE = os.environ.get("DATA_SOURCE", "yfinance")

# --- Angel One SmartAPI credentials (only used if DATA_SOURCE="angelone") ---
# Get these from https://smartapi.angelbroking.com/apps (API key) and your
# Angel One account (client code, trading PIN). ANGEL_TOTP_SECRET is the
# base32 secret behind the TOTP QR code shown when you enable 2FA -- NOT a
# live 6-digit code, which expires in seconds. Never commit real values here;
# set them as environment variables instead.
ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "")
ANGEL_CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE", "")
ANGEL_PIN = os.environ.get("ANGEL_PIN", "")
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "")

# Maps this app's INTERVAL setting (config.py, top of file) to Angel One's
# interval enum for getCandleData.
ANGEL_INTERVAL_MAP = {
    "1m": "ONE_MINUTE",
    "3m": "THREE_MINUTE",
    "5m": "FIVE_MINUTE",
    "10m": "TEN_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "1d": "ONE_DAY",
}

# Angel One rejects a request for more history than this per interval --
# used to automatically clamp LOOKBACK_PERIOD so fetches don't fail outright.
# (Source: Angel One's published historical-data limits; verify against
# current docs at https://smartapi.angelbroking.com/docs/Historical since
# these have changed before.)
ANGEL_MAX_DAYS = {
    "ONE_MINUTE": 30,
    "THREE_MINUTE": 60,
    "FIVE_MINUTE": 100,
    "TEN_MINUTE": 100,
    "FIFTEEN_MINUTE": 200,
    "THIRTY_MINUTE": 200,
    "ONE_HOUR": 400,
    "ONE_DAY": 2000,
}

# getCandleData is rate-limited (3 req/sec, 180 req/min as of this writing).
# Indices don't have a normal "-EQ" equity listing, so their
# (exchange, symboltoken) pairs are hardcoded here rather than looked up in
# the instrument master. Verify tokens against Angel's scrip master
# (https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json)
# if they ever stop resolving -- Angel doesn't guarantee these are stable.
ANGEL_INDEX_TOKENS = {
    "^NSEI": ("NSE", "99926000"),     # Nifty 50
    "^NSEBANK": ("NSE", "99926009"),  # Bank Nifty
    "^CNXFIN": ("NSE", "99926037"),   # Fin Nifty
    "^BSESN": ("BSE", "99919000"),    # Sensex
}
ANGEL_MIN_REQUEST_INTERVAL_SECONDS = 0.4  # ~150/min, safely under the 180/min cap

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

# --- Chart pattern detection (5th signal condition) ---
# Alongside the swing-high/low breakout, the app also looks for classic
# chart patterns (Double Top/Bottom, Head & Shoulders, Triangles) and
# candlestick reversal patterns (Engulfing, Hammer, Shooting Star). Together
# they form the 5th vote in signals.py -- see chart_patterns.py.
PATTERN_PIVOT_WINDOW = 3        # bars on each side required to confirm a swing pivot
PATTERN_LOOKBACK = 40           # how many recent bars to scan for pivots/patterns
PATTERN_PRICE_TOLERANCE = 0.02  # 2%: how close two peaks/troughs must be to "match"
PATTERN_TRIANGLE_MIN_TOUCHES = 3  # min pivot highs AND lows needed to fit a triangle trendline

# --- Supertrend (6th signal condition) ---
# ATR-based trend-following line, popular for intraday NSE trading. Unlike
# the SMA vote (which reports the current trend, every bar), Supertrend
# votes only on the bar where the trend actually FLIPS direction -- so it
# behaves more like a timing signal (similar to the MACD crossover) than a
# standing filter. Uses its own ATR period/multiplier, independent of
# ATR_PERIOD above (10/3 is the standard textbook combo).
ST_PERIOD = 10
ST_MULTIPLIER = 3

# --- VWAP (7th signal condition) ---
# Volume Weighted Average Price, reset each trading session (day). A simple,
# widely-used intraday fair-value reference: price above VWAP = bullish
# bias, below = bearish bias. Automatically skipped for symbols with no real
# volume data (indices), same as the breakout volume check.

# --- Volume confirmation ---
# A breakout only counts toward the vote if volume is meaningfully above its
# recent average -- a breakout on weak volume is much less reliable. This is
# automatically skipped for symbols with no real volume data (indices report
# 0 volume via yfinance), so it only applies to individual stocks.
VOLUME_MA_PERIOD = 20
VOLUME_CONFIRMATION_MULTIPLIER = 1.5

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
