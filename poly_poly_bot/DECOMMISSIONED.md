# Decommissioned strategies

On **2026-06-17** the bot was reduced to **Strategy #1 (Copy Trading)** only.
Two strategies were removed:

- **Strategy #2 — Weather Betting** (NOAA ensemble forecasts on temperature markets)
- **Strategy #3 — Tennis Arbitrage** (sharp bookmaker odds vs. Polymarket prices)

Everything still runs for Strategy #1: the live copy trader plus the two
measurement-only harnesses (copy-paper validation and wallet discovery).

## What was removed

Source:
- `src/weather/` — entire package (Strategy #2)
- `src/tennis/` — entire package (Strategy #3 scanner, paper book, order placer, discovery cache)
- `src/odds/` — sharp-odds providers (Smarkets, BetsAPI, Pinnacle) — used only by tennis
- `src/polymarket/` — `rtds_stream.py` RTDS WebSocket book mirror — used only by the tennis streaming engine
- `src/runtime_state.py` — per-strategy preview/live toggle — used only by tennis (Strategy #1 uses `PREVIEW_MODE` directly)
- `backtest/tennis_backtest.py`
- `scripts/clob_books_bench.py` — tennis CLOB benchmark
- Tests: `test_tennis_arb.py`, `test_paper_book.py`, `test_order_placer.py`,
  `test_discovery_cache.py`, `test_smarkets_provider.py`, `test_betsapi_provider.py`,
  `test_pinnacle_rapidapi.py`, `test_rtds_stream.py`, `test_pattern_detector.py` (weather)

Wiring stripped from `main.py`, `src/config.py`, `src/telegram_bot.py`:
- Strategy #2/#3 enable flags, weather config, tennis/Smarkets/BetsAPI/Pinnacle/RTDS config
- The weather scheduler, the tennis scanner + streaming loops, and `--once` mode
- Telegram commands `/predict`, `/tennis`, `/tennis_pnl`, `/takeprofit`, `/mode`,
  `/live`, `/preview` and their menu entries

## How to restore from git

All of the above lives intact at commit **`cf87f93`** (the commit immediately
before the decommission). To bring a strategy back:

```bash
# See exactly what the decommission commit changed
git show <decommission-commit>

# Restore the tennis package (and/or weather/, odds/, polymarket/) as it was
git checkout cf87f93 -- poly_poly_bot/src/tennis poly_poly_bot/src/odds \
    poly_poly_bot/src/polymarket poly_poly_bot/src/runtime_state.py

# Restore the matching tests
git checkout cf87f93 -- poly_poly_bot/tests/test_tennis_arb.py \
    poly_poly_bot/tests/test_paper_book.py  # ...etc

# For weather instead:
git checkout cf87f93 -- poly_poly_bot/src/weather \
    poly_poly_bot/tests/test_pattern_detector.py
```

After restoring files you must also re-add the wiring (imports, threads,
config keys, Telegram commands) — the cleanest reference is the full
pre-decommission versions of `main.py`, `src/config.py`, and
`src/telegram_bot.py`:

```bash
git show cf87f93:poly_poly_bot/main.py
git show cf87f93:poly_poly_bot/src/config.py
git show cf87f93:poly_poly_bot/src/telegram_bot.py
git show cf87f93:poly_poly_bot/.env.example   # for the removed config keys
```
