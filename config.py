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
#
# Lowered from 25 to 15 based on diagnostic evidence: diagnostic_backtest.py
# showed ADX=25 produced only 1 trade across Nifty/BankNifty/Sensex over
# ~60 days, while ADX=15 produced 6 (2W/4L, 33.3% win rate -- too small a
# sample to be conclusive on quality, but confirms ADX was the dominant
# bottleneck, not the 4-of-7 vote threshold). Watch PAPER_TRADING results
# at this setting; raise back toward 25 if the win rate stays weak once a
# larger sample accumulates, since more signals at a worse win rate isn't
# actually an improvement.
ADX_PERIOD = 14
ADX_THRESHOLD = 15

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

# =====================================================================
# --- Automated options trading (Nifty / Bank Nifty / Sensex only) ---
# =====================================================================
# Paper trading by default -- simulates order placement/exit using REAL
# premiums from Angel One, but never sends a real order to the exchange.
# Set the PAPER_TRADING env var to "false" only once you've watched this
# run and trust it -- see README.
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() != "false"

# Which symbols get auto-traded (as opposed to just alerted on). A subset
# of SYMBOLS above -- the rest of the watchlist still generates signals and
# Telegram alerts via position_tracker.py as before, just without options
# orders being placed.
TRADE_SYMBOLS = ["^NSEI", "^NSEBANK", "^BSESN"]

# Lot sizes as of the Jan 2026 NSE/BSE revision -- NSE reviews these
# roughly twice a year, so re-verify periodically.
LOT_SIZES = {
    "^NSEI": 65,
    "^NSEBANK": 30,
    "^BSESN": 20,
}

# Angel One's instrument-master "name" field for each index's option chain,
# and which exchange segment lists it (BSE indices trade options on BFO,
# NSE indices on NFO).
OPTION_UNDERLYING_NAME = {
    "^NSEI": "NIFTY",
    "^NSEBANK": "BANKNIFTY",
    "^BSESN": "SENSEX",
}
OPTION_EXCHANGE_SEGMENT = {
    "^NSEI": "NFO",
    "^NSEBANK": "NFO",
    "^BSESN": "BFO",
}

# Target/stop are based on the option PREMIUM itself (real data from Angel
# One), not the underlying's price.
PREMIUM_TARGET_PCT = 30.0   # exit with a win once premium rises this %
PREMIUM_STOP_PCT = 15.0     # exit with a loss once premium falls this %

# Position sizing: each trade risks roughly RISK_PER_TRADE rupees (sized so
# a full stop-loss hit loses approximately this much), capped at
# MAX_LOTS_PER_TRADE lots regardless. If even 1 lot's stop-loss risk
# exceeds RISK_PER_TRADE by more than 50%, the trade is skipped rather than
# silently taken at an oversized risk -- see paper_broker.py.
CAPITAL = 15000.0
RISK_PER_TRADE = 1500.0
MAX_LOTS_PER_TRADE = 3

# Daily risk limits for the options auto-trading path specifically
# (separate from, and in addition to, the alerts-only position_tracker.py
# limits that may apply to the rest of the watchlist).
MAX_TRADES_PER_DAY = 5
MAX_OPEN_POSITIONS = 2
DAILY_LOSS_LIMIT = 1500.0

# Force-exit all open paper positions by this time (IST) regardless of
# target/stop -- standard intraday options discipline, avoids holding into
# the last volatile minutes before close.
FORCE_EXIT_HOUR = 15
FORCE_EXIT_MINUTE = 15
