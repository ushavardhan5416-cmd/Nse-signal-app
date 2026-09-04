# NSE Trading Signals App (Starter)

An alerts-only trading signals app for NSE stocks: pulls price data, computes
RSI/MACD/SMA, and pushes BUY/SELL alerts to Telegram. It does **not** place
orders — you stay in control of execution.

## Setup

```bash
pip install -r requirements.txt
```

1. Edit `config.py`:
   - Add/remove symbols in `SYMBOLS` (use the `.NS` suffix, e.g. `RELIANCE.NS`)
   - Tune `INTERVAL`, RSI/MACD/SMA parameters as you like
2. Set up Telegram alerts (optional but recommended):
   - Create a bot via [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
   - Message your new bot once, then visit
     `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`
   - Put both into `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `config.py`
   - If you skip this, signals just print to the console instead

## Run

```bash
# Sanity-check the strategy against history before trusting it live
python backtest.py

# Start the live polling loop (run during NSE market hours: 9:15am-3:30pm IST)
python main.py
```

## How it works

- `data_fetch.py` — pulls OHLCV candles (currently via `yfinance`, free but
  delayed data — good for prototyping)
- `indicators.py` — computes RSI, MACD, SMA on the price series
- `signals.py` — a simple voting system: needs 2 of 3 indicators to agree
  before calling BUY or SELL, otherwise HOLD
- `notifier.py` — formats and sends alerts to Telegram
- `backtest.py` — walks through history bar-by-bar and simulates a naive
  long-only strategy so you can eyeball whether the logic has any edge
  before trusting it
- `main.py` — ties it together in a polling loop

## Moving to real-time / production data

`yfinance` data is delayed and not reliable enough for anything beyond
prototyping. For real-time NSE data, swap `data_fetch.py` for a broker API:

- [Zerodha Kite Connect](https://kite.trade/) — most popular, well-documented
- [Upstox API](https://upstox.com/developer/api-documentation/)
- [Angel One SmartAPI](https://smartapi.angelbroking.com/)

Keep the function signature `fetch_ohlcv(symbol) -> DataFrame` the same and
nothing else in the app needs to change.

## Running it from your phone (via cloud deployment)

The engine isn't practical to run directly on iOS, and awkward on Android.
Instead, deploy it to a free/cheap always-on host and just receive alerts on
your phone through Telegram.

### Option A: Railway (easiest, has a free trial)

1. Push this folder to a GitHub repo (or use Railway's CLI to deploy a local folder)
2. On [railway.app](https://railway.app), create a new project → "Deploy from GitHub repo"
3. Railway will detect the `Dockerfile` and build automatically
4. In the project's **Variables** tab, add:
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat id
5. Deploy — it runs `main.py` continuously as a background worker, no server management needed
6. You'll get Telegram alerts on your phone with zero battery/network burden on the phone itself

### Option B: Render (similar, also has a free/low-cost tier)

Same idea as Railway: connect your GitHub repo, Render detects the
`Dockerfile`, add the same two environment variables in the dashboard, deploy
as a "Background Worker" (not a "Web Service", since this app doesn't serve
HTTP requests).

### Option C: A cheap VPS (DigitalOcean, Hetzner, etc.)

```bash
git clone <your-repo-url>
cd nse_signals_app
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
nohup python3 main.py &   # keeps running after you disconnect
```

Either way — once deployed, your phone's job is just to have the Telegram
app installed and notifications turned on.

## Important: if you plan to auto-place orders

This starter is alerts-only by design. If you extend it to place orders
automatically via a broker API, SEBI's April 2026 algo trading framework
applies to you:

- Every algo order needs an exchange-assigned **Algo-ID**
- Your broker must approve/empanel the strategy — you can't just plug into
  the exchange directly
- API access requires a **whitelisted static IP**, **OAuth login**, and
  **mandatory 2FA**; sessions must reset daily before market pre-open
- If you distribute the strategy to others without disclosing its logic
  (a "black box" algo), the provider needs a SEBI Research Analyst license

None of this applies if you keep it alerts-only and place trades yourself.

## Disclaimer

This is a technical starting point, not investment advice. The included
strategy (RSI + MACD + SMA voting) is a simple illustration, not a proven
edge — backtest thoroughly, paper-trade before risking real capital, and
never rely on unverified signals for financial decisions.
