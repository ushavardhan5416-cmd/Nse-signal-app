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

## Chart patterns: breakout + classic/candlestick patterns

Two of the five conditions are chart patterns:

**4th condition — breakout.** The close must break above the highest high of
the prior 20 candles (bullish) or below the lowest low of the prior 20
candles (bearish) — `BREAKOUT_LOOKBACK` in `config.py` controls the window.
For stocks (real volume data), the breakout only counts if it happens on
above-average volume (`VOLUME_CONFIRMATION_MULTIPLIER`); indices report 0
volume via yfinance so this check is skipped for them.

**5th condition — classic + candlestick patterns** (`chart_patterns.py`).
Bars are first reduced to "swing pivots" (local highs/lows confirmed a few
candles on either side), and each pattern below is a specific arrangement of
2-3 recent pivots:

- **Double Top / Double Bottom** — two similar-height peaks (or similar-depth
  troughs) with a neckline between them, confirmed once price closes past
  the neckline.
- **Head & Shoulders / Inverse Head & Shoulders** — a taller "head" between
  two roughly equal "shoulders", confirmed on a neckline break.
- **Triangles** (ascending / descending / symmetrical) — a trendline fit
  through recent swing highs and recent swing lows; confirmed once price
  breaks out beyond the relevant trendline.
- **Candlestick reversals** (Bullish/Bearish Engulfing, Hammer, Shooting
  Star) — checked last, as a fallback, since single/two-candle patterns are
  the noisiest of the group, especially on a 15-minute timeframe.

Only the first confirmed pattern (checked in the priority order above) casts
the 5th vote — patterns that are still "forming" (no neckline/trendline
break yet) don't count. `PATTERN_PIVOT_WINDOW`, `PATTERN_LOOKBACK`,
`PATTERN_PRICE_TOLERANCE`, and `PATTERN_TRIANGLE_MIN_TOUCHES` in `config.py`
control the detection sensitivity. As with everything else here, these are
heuristic detectors, not a guarantee the pattern is "real" — backtest before
trusting them.

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
strict 3-of-5 rule), you'll still see a target/stop-loss and CE/PE view
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

## Supertrend + VWAP (6th & 7th signal conditions)

Two more conditions were added to the vote, bringing it to **7 total** —
the bar to fire a signal moved from 3-of-5 to **4-of-7** (roughly the same
~60% threshold as before).

**Supertrend** (`ST_PERIOD`/`ST_MULTIPLIER` in `config.py`, 10/3 by
default) is an ATR-based trend-following line. Unlike the SMA vote, which
reports the *standing* trend on every bar, Supertrend only votes on the bar
where the trend actually **flips** direction — so it behaves like a timing
signal (similar to the MACD crossover) rather than another standing filter.

**VWAP** (Volume Weighted Average Price) is a session-based fair-value
reference — it resets at the start of each trading day and accumulates
`(typical price × volume)` through the session. Price above VWAP votes
bullish, below votes bearish. Like the breakout volume check, this is
automatically skipped for indices (no real volume data via yfinance), so
they're voted on by the remaining 6 conditions.

## Signal quality filters: ADX + volume confirmation

Two filters were added on top of the core RSI/MACD/SMA/breakout/pattern
system to cut down false signals:

**ADX (trend strength gate).** ADX measures how strongly a trend is
developing, regardless of direction — it doesn't vote bullish or bearish
itself, it gates whatever the other 5 conditions already decided. If ADX is
below `ADX_THRESHOLD` (default 25, the standard textbook cutoff) when a
BUY/SELL would otherwise fire, the signal is suppressed back to HOLD. This
targets the most common failure mode for RSI/MACD-style signals: firing in
a flat, choppy market where they whipsaw back and forth. Lower the
threshold in `config.py` to catch more (weaker) trends; raise it to be more
selective.

**Volume confirmation on breakouts.** A breakout above/below the recent
swing high/low only counts toward the vote if it happens on meaningfully
above-average volume (`VOLUME_CONFIRMATION_MULTIPLIER`, default 1.5× the
20-period average). A breakout on thin volume is much less reliable — often
just noise rather than real buying/selling pressure. **This only applies to
individual stocks** — indices report 0 volume via yfinance, so there's
nothing meaningful to check, and the requirement is automatically skipped
for them (you'll see "volume confirmed" in the reasons for a stock, and no
such note for an index breakout).

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
- `indicators.py` — computes RSI, MACD, SMA, ATR, ADX, Supertrend, VWAP, and
  rolling volume average on the price series
- `chart_patterns.py` — detects Double Top/Bottom, Head & Shoulders,
  Triangles, and candlestick reversal patterns (Engulfing/Hammer/Shooting
  Star) from swing pivots
- `signals.py` — requires **at least 4 of the 7 conditions to agree** (RSI at
  an extreme, a fresh MACD crossover, SMA trend, a breakout above/below the
  recent swing high/low, a confirmed chart pattern from `chart_patterns.py`,
  a fresh Supertrend flip, and price vs VWAP) before calling BUY or SELL. Two
  additional filters
  sit on top: a **breakout only counts on above-average volume** (stocks
  only — indices have no real volume data, so this check is automatically
  skipped for them), and an **ADX gate** suppresses the whole signal back to
  HOLD if ADX indicates the market isn't trending strongly enough,
  regardless of how the votes came out. Otherwise HOLD, and HOLD signals
  never trigger a Telegram alert. Every BUY/SELL alert also states exactly
  which conditions voted for it (e.g. "4/7 conditions agree: RSI oversold;
  MACD bullish crossover; Chart pattern: Bullish Engulfing; Supertrend
  flipped bullish"). BUY/SELL
  signals also get a
  target price and stop-loss, sized off ATR so they scale with each stock's
  actual volatility (see below)
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
- [Angel One SmartAPI](https://smartapi.angelbroking.com/) — **built in**,
  see below

Keep the function signature `fetch_ohlcv(symbol) -> DataFrame` the same and
nothing else in the app needs to change.

## Using Angel One SmartAPI for data

The app can pull data from Angel One's SmartAPI instead of yfinance —
`angelone_fetch.py` implements this as a drop-in replacement (same
`fetch_ohlcv(symbol)` / `fetch_all(symbols)` shape yfinance uses, so
`signals.py`, `backtest.py`, `main.py`, and `telegram_listener.py` don't
need any changes).

**Requirements:**
- A funded Angel One trading account with API access enabled
- An API key from [smartapi.angelbroking.com/apps](https://smartapi.angelbroking.com/apps)
- Your client code and trading PIN
- 2FA/TOTP enabled on your account — you need the **base32 secret** behind
  the QR code (shown once when you enable it), not a live 6-digit code

**Setup:**

1. Install the extra dependencies (already in `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```
2. Set these environment variables (don't hardcode them in `config.py`):
   ```bash
   export DATA_SOURCE="angelone"
   export ANGEL_API_KEY="your_api_key"
   export ANGEL_CLIENT_CODE="your_client_code"
   export ANGEL_PIN="your_trading_pin"
   export ANGEL_TOTP_SECRET="your_totp_base32_secret"
   ```
3. Run as usual (`python backtest.py` / `python main.py`) — `data_fetch.py`
   automatically routes to `angelone_fetch.py` when `DATA_SOURCE=angelone`.

**Important differences from yfinance:**
- **No batch endpoint.** Angel One fetches one symbol per request, rate
  limited to roughly 3/sec — a ~180-symbol watchlist takes a couple of
  minutes per cycle, not seconds. If you expand the watchlist much further,
  raise `POLL_INTERVAL_SECONDS` in `config.py` accordingly.
- **Symbol resolution.** Angel needs a numeric `symboltoken`, not a plain
  ticker. `angelone_fetch.py` downloads Angel's instrument master once
  (cached to disk, refreshed daily) and maps our `"RELIANCE.NS"`-style
  tickers to it automatically for NSE equities. Indices (Nifty, Bank Nifty,
  Sensex, Fin Nifty) use hardcoded tokens in `ANGEL_INDEX_TOKENS`
  (`config.py`) since they aren't in the equity instrument master — verify
  these against Angel's [scrip master](https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json)
  if they ever stop resolving.
- **History limits.** Angel caps how much history you can request per
  candle interval (e.g. 30 days for 1-minute candles, 200 days for 15-minute
  — see `ANGEL_MAX_DAYS` in `config.py`). `LOOKBACK_PERIOD` is automatically
  clamped to whatever Angel allows for your configured `INTERVAL`.
- **Session handling.** Angel sessions are re-established automatically
  (roughly every 8 hours in this implementation); you don't need to restart
  the app daily yourself, but Angel's own servers still enforce their
  standard session/token expiry rules independently.
- **This module wasn't tested against Angel One's live servers** while
  building it (no account/credentials available in the environment it was
  built in) — it was implemented against their documented request/response
  format and unit tested with mocked responses. Test it against your own
  account with a small watchlist before trusting it for anything live.

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
