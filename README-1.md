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

## Signal quality filters: ADX + volume confirmation

Two filters were added on top of the core RSI/MACD/SMA/breakout system to
cut down false signals:

**ADX (trend strength gate).** ADX measures how strongly a trend is
developing, regardless of direction — it doesn't vote bullish or bearish
itself, it gates whatever the other 4 conditions already decided. If ADX is
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

## Chart patterns (5th condition)

On top of the breakout check, the app now scans for:

- **Candlestick patterns**: bullish/bearish engulfing, hammer, shooting star
  (checked on the latest 1-2 candles)
- **Double top / double bottom**: two peaks or troughs of similar height
  with a meaningful reversal between them, confirmed only once price
  actually breaks the neckline
- **Head & shoulders / inverse head & shoulders**: three peaks (or troughs)
  with the middle one most extreme, confirmed on a neckline break

These feed into the same vote as breakout detection — checked in order of
significance (head & shoulders → double top/bottom → candlestick), and the
first match found counts as the 5th condition. All are confirmed only on
an actual neckline/level break on the current bar, not just on the shape
existing somewhere in recent history.

## Risk management

Inspired by comparing this app against another NIFTY options tool: three
basic discipline controls now cap how many new positions open per day,
regardless of how many signals fire (`config.py`):

- `MAX_TRADES_PER_DAY` (default 5) — new positions opened per day, across
  all symbols combined
- `MAX_OPEN_POSITIONS` (default 3) — concurrent open positions at once,
  across all symbols
- `DAILY_LOSS_LIMIT_PCT` (default 3%) — once the day's **estimated** P&L
  drops below this, no new positions open until the next trading day

**Important honesty note on the P&L figure:** this app doesn't buy real
option premiums or manage real capital — it only tracks the underlying's
price. The "estimated P&L" is a proxy: it applies the underlying's actual
% move from entry to exit to an assumed notional capital
(`ASSUMED_CAPITAL_PER_TRADE`, default ₹15,000), purely so the daily loss
limit has something concrete to check against. It is illustrative, not a
real premium-based P&L — don't treat the rupee figures in target-hit/
stop-hit alerts or the daily summary as what you'd actually make or lose
trading options.

When a daily limit is hit, you'll get one notification (not repeated every
cycle) and existing open positions keep being tracked normally — only new
positions are blocked for the rest of the day.

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
- `indicators.py` — computes RSI, MACD, SMA, ATR, ADX, and rolling volume
  average on the price series
- `signals.py` — requires **at least 3 of the 5 conditions to agree** (RSI at
  an extreme, a fresh MACD crossover, SMA trend, a breakout above/below the
  recent swing high/low, and a chart pattern — candlestick, double top/bottom,
  or head & shoulders) before calling BUY or SELL — otherwise HOLD, and HOLD
  signals never trigger a Telegram alert. Every alert clearly states which
  named conditions drove the call (e.g. "Recommended based on 3/5: RSI, MACD,
  Chart Pattern"). BUY/SELL signals also get a target price and stop-loss,
  sized off ATR so they scale with each stock's actual volatility (see below)
- `notifier.py` — formats and sends alerts to Telegram
- `backtest.py` — walks through history bar-by-bar and simulates a naive
  long-only strategy so you can eyeball whether the logic has any edge
  before trusting it
- `main.py` — ties it together in a polling loop

## Real-time data via Angel One SmartAPI

`yfinance` data is delayed ~15-20 minutes — fine for prototyping, not for
anything time-sensitive. If you have an Angel One trading account, the app
can pull much less-delayed data from your own account instead.

**This is a toggle, not a rewrite.** Set `DATA_SOURCE` and it switches the
whole app over — nothing else changes, and you can switch back to
`yfinance` any time if something looks off.

### Setup

1. Get your SmartAPI credentials (see Anthropic's earlier walkthrough, or
   [smartapi.angelbroking.com](https://smartapi.angelbroking.com/)): Client
   ID, trading password, API Key, and TOTP secret (from the enable-totp page)
2. In Railway → your service → **Variables** tab, add:
   - `DATA_SOURCE` = `angelone`
   - `ANGEL_CLIENT_CODE` = your Angel One client ID
   - `ANGEL_API_KEY` = your SmartAPI key
   - `ANGEL_PASSWORD` = your trading password/MPIN
   - `ANGEL_TOTP_SECRET` = the TOTP secret from the enable-totp page
3. **If you're on a Railway free/hobby plan**, Angel One's SmartAPI requires
   a whitelisted static IP. Add that IP to your SmartAPI app's allowed-IPs
   list (see earlier conversation for the static-IP setup — either Railway's
   own Static Outbound IPs on the Pro plan, or a proxy add-on like QuotaGuard
   or a static-IP provider such as staticip.in)
4. Save — Railway auto-redeploys with the new settings

### What changed under the hood

- `angel_client.py` handles SmartAPI login (TOTP-based, session cached and
  auto-retried once if it expires mid-run), resolves each symbol to Angel
  One's exchange+token (indices use a fixed lookup table; stocks are
  resolved dynamically against Angel One's instrument master, so it keeps
  working even if a stock's token changes later), and fetches candle data
  one symbol at a time (Angel One's historical API doesn't support batch
  requests the way yfinance does, hence a polite delay between each call —
  `ANGEL_REQUEST_DELAY_SECONDS` in `config.py`)
- `data_fetch.py` branches on `DATA_SOURCE` but returns the exact same
  DataFrame shape either way, so `indicators.py`, `signals.py`,
  `notifier.py`, and `position_tracker.py` don't need to know or care
  which source is active

### If something goes wrong

Set `DATA_SOURCE` back to `yfinance` in Railway's Variables tab — the app
falls back immediately, no other changes needed. Common issues:
- **Login fails**: double-check all 4 credentials, especially the TOTP
  secret (it's the raw secret key from the QR code setup, not a 6-digit code)
- **A specific stock fails but others work**: that stock's listing wasn't
  found in Angel One's instrument master under the expected NSE `-EQ`
  format — check the logs for which symbol, and verify its actual Angel
  One trading symbol
- **Everything fails with an IP-related error**: your static IP isn't
  correctly whitelisted in your SmartAPI app settings, or Railway's egress
  IP changed (can happen if you change regions)

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
