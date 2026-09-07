# NSE Trading Signals App (Starter)

An alerts-only trading signals app for NSE stocks: pulls price data, computes
RSI/MACD/SMA, and pushes BUY/SELL alerts to Telegram. It does **not** place
orders — you stay in control of execution.

## Setup

```bash
pip install -r requirements.txt
```

1. Edit `config.py`:
   - Tune `INTERVAL`, RSI/MACD/SMA parameters as you like
   - The watchlist itself lives in `symbols_fo.txt` (see below), not `config.py`
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

## Chart pattern: breakout confirmation

The 4th required condition is a **breakout pattern**: the close must break
above the highest high of the prior 20 candles (bullish) or below the lowest
low of the prior 20 candles (bearish) — `BREAKOUT_LOOKBACK` in `config.py`
controls the window.

Breakouts were chosen over other chart patterns because they're reliable to
detect mechanically from OHLC data alone. Candlestick patterns (engulfing,
hammer, etc.) are noisy at a 15-minute timeframe, and classic chart patterns
(head & shoulders, double top/bottom, triangles) need peak/trough detection
across many more candles and are unreliable to auto-detect without a lot
more logic and false positives. A swing-high/low breakout is a clean,
well-defined signal that plugs into the same voting system as the other
three indicators.

## Alert window (trading hours only)

Alerts (and the fetch/signal cycle itself) only run **Mon–Fri, 8:30 AM–5:00
PM IST** by default — configurable via `ALERT_START_HOUR`, `ALERT_START_MINUTE`,
`ALERT_END_HOUR`, `ALERT_END_MINUTE` in `config.py`. This works correctly
regardless of what timezone the server itself runs in (Railway runs in
UTC) — the check always converts to IST explicitly.

NSE market holidays aren't detected automatically. If you want the app to
skip specific holidays too, add them to `MARKET_HOLIDAYS` in `config.py` as
`"YYYY-MM-DD"` strings.

## Index signals (Nifty/Bank Nifty/Sensex) — bug fix

Earlier versions could silently drop all index data: yfinance often returns
`NaN` for index volume (indices don't have a traded volume the way stocks
do), and the old cleaning step dropped any row with *any* missing value —
wiping out index data even though the price data itself was perfectly
valid. This is fixed: missing price data still gets dropped, but missing
Volume is now filled with 0 instead of dropping the row.

## Target/stop-loss hit notifications & daily summary

When a BUY/SELL signal fires, the app now tracks it as an open position and
checks it against the price on every subsequent cycle. You'll get a
notification the moment it hits target or stop-loss:

```
✅ TARGET HIT — RELIANCE.NS
BUY entry: ₹1000.00
Now: ₹1030.00
Target was: ₹1025.00
```

At **3:30 PM IST** each trading day (configurable via `SUMMARY_HOUR` /
`SUMMARY_MINUTE` in `config.py`), you'll get a daily summary and the
counters reset for the next day:

```
📊 Daily Summary — 2026-09-05
✅ Targets hit: 3
🛑 Stop-losses hit: 1
Win rate: 75%
```

**Important limitations:**
- Only one open position per symbol at a time — if a symbol already has an
  open position, a new BUY/SELL signal for it won't open a second one
  until the first is closed (target or stop hit)
- Checked once per polling cycle (every 15 min by default), not tick-by-tick
  — if price spikes through target and back within one cycle, it may be
  missed
- **State lives in memory only** — it resets if the app restarts or
  Railway redeploys mid-day (open positions and the day's counters are
  lost). This is a lightweight tracker for the app's own alerts, not a
  replacement for checking your actual broker positions

## Ask about any stock on demand

Besides scheduled alerts, you can now message the bot directly to check any
stock or index right now:

```
RELIANCE
/check TCS
NIFTY / BANKNIFTY / SENSEX
/help
```

It fetches fresh data and replies with the current signal (BUY/SELL/HOLD,
reasons, target/stop-loss and CE/PE view if applicable) — same format as
the scheduled alerts. Even for a HOLD (the most common result, given the
strict 3-of-4 rule), you'll still see a target/stop-loss and CE/PE view
based on the currently leaning direction — clearly labeled as a reference
level rather than a confirmed signal, since HOLD never triggers a real
BUY/SELL. This works independently of the alert window, so you can check a
stock any time; just note that outside market hours the price data itself
may be stale (whatever NSE last traded).

Only messages from your configured `TELEGRAM_CHAT_ID` are answered — this
stops random people who find your bot's username from being able to query
it and rack up API calls.

## Options view (CE/PE)

BUY/SELL alerts now include a directional options suggestion:

```
📈 Options view: CE around ₹24550 strike
```

- **BUY → CE** (call option), **SELL → PE** (put option)
- The strike shown is an approximate ATM (at-the-money) strike, rounded
  from the underlying's current price — known indices use their real
  strike interval (`STRIKE_INTERVALS` in `config.py`: Nifty=50, Bank
  Nifty/Sensex=100), other symbols use a rough price-based heuristic

**Important limitation:** this is a *directional* suggestion based only on
the underlying's price — the app has no access to live option premiums,
open interest, implied volatility, or the actual option chain (yfinance
doesn't provide NSE options data). Option premiums don't move 1:1 with the
underlying and are also affected by time decay and IV changes, so the
target/stop-loss shown are underlying-price levels, **not** option premium
targets. Always check actual strike prices, premiums, and liquidity on your
broker's terminal before placing an options trade.

## Target price & stop-loss

BUY/SELL alerts now include a suggested target and stop-loss, e.g.:

```
🟢 BUY — RELIANCE.NS
Price: ₹1000.00
🎯 Target: ₹1025.00
🛑 Stop-loss: ₹985.00
Risk:Reward ≈ 1:1.7
```

These are calculated from **ATR (Average True Range)** — a volatility
measure — rather than a fixed percentage, so a volatile stock gets wider
levels than a stable one automatically:

- `target = entry price + (ATR × ATR_TARGET_MULTIPLIER)` for BUY (inverse for SELL)
- `stop_loss = entry price − (ATR × ATR_STOP_MULTIPLIER)` for BUY (inverse for SELL)

Defaults in `config.py` (`ATR_TARGET_MULTIPLIER = 2.5`, `ATR_STOP_MULTIPLIER
= 1.5`) give roughly a 1:1.67 risk:reward ratio. Adjust these to taste — a
higher target multiplier aims for bigger moves but hits less often; a
tighter stop multiplier limits downside but risks getting stopped out by
normal noise. **These levels are a mechanical calculation from recent
volatility, not a guarantee the trade will reach them** — always sanity
check against support/resistance and news before acting on them.

## Watchlist: F&O stocks + indices

`symbols_fo.txt` holds the full watchlist — one symbol per line, `#` for
comments. It currently includes:

- **Indices**: NIFTY 50 (`^NSEI`), Bank Nifty (`^NSEBANK`), Sensex (`^BSESN`)
- **~175 NSE F&O stocks** across large caps, banks/NBFCs, IT, auto, pharma,
  metals, energy, infra, and more

**This list will drift out of date.** NSE reviews F&O eligibility
periodically (roughly quarterly) and adds/removes names based on liquidity
criteria — recent examples: 8 stocks added April 2026, Exide Industries and
Nuvama Wealth removed July 2026. To refresh the list:

1. Visit NSE's official current list: https://www.nseindia.com/market-data/list-underlying-securities-derivatives
2. Download the CSV/list of underlying securities
3. Update `symbols_fo.txt` — for each stock symbol, append `.NS` (e.g. `RELIANCE` → `RELIANCE.NS`); indices keep their `^` ticker (see the top of the file)

With ~180 symbols, the app fetches in batches (`BATCH_SIZE` in `config.py`,
default 40 per batch) rather than one-by-one — this is both faster and less
likely to trip yfinance's informal rate limits. Increase `POLL_INTERVAL_SECONDS`
in `config.py` if you expand the list much further and fetches start taking
too long per cycle.

## How it works

- `data_fetch.py` — pulls OHLCV candles (currently via `yfinance`, free but
  delayed data — good for prototyping)
- `indicators.py` — computes RSI, MACD, SMA, and ATR (Average True Range) on
  the price series
- `signals.py` — requires **at least 3 of the 4 conditions to agree** (RSI at
  an extreme, a fresh MACD crossover, SMA trend, and a breakout above/below
  the recent swing high/low) before calling BUY or SELL — otherwise HOLD,
  and HOLD signals never trigger a Telegram alert. BUY/SELL signals also
  get a target price and stop-loss, sized off ATR so they scale with each
  stock's actual volatility (see below)
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
