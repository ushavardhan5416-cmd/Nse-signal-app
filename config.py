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

# --- Alerting ---
# Create a bot via @BotFather on Telegram, then message it once and fetch your
# chat_id via https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PUT_YOUR_TELEGRAM_CHAT_ID_HERE")

# --- Run mode ---
# How often (seconds) the polling loop re-checks the market in `main.py`.
POLL_INTERVAL_SECONDS = 900  # 15 minutes, matches INTERVAL by default
