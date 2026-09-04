"""
Central configuration for the NSE signals app.
Edit the values below before running.
"""

import os

# --- Watchlist ---
# yfinance uses the ".NS" suffix for NSE-listed stocks (e.g. Reliance -> RELIANCE.NS)
SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
]

# --- Data settings ---
INTERVAL = "15m"      # candle interval: 1m, 5m, 15m, 1h, 1d ...
LOOKBACK_PERIOD = "5d" # how much history to pull each run (yfinance limits intraday history)

# --- Indicator settings ---
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

SMA_SHORT = 20
SMA_LONG = 50

# --- Alerting ---
# Create a bot via @BotFather on Telegram, then message it once and fetch your
# chat_id via https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PUT_YOUR_TELEGRAM_CHAT_ID_HERE")

# --- Run mode ---
# How often (seconds) the polling loop re-checks the market in `main.py`.
POLL_INTERVAL_SECONDS = 900  # 15 minutes, matches INTERVAL by default
