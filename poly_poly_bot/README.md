# Poly Poly Bot v2.0

Polymarket copy-trading bot (Strategy #1), running as a single Python process.

## Overview

| Strategy | Description | Signal Source |
|----------|-------------|---------------|
| **1 - Copy Trading** | Copy insider/whale trades with tiered risk (1a geopolitical insiders, 1b leaderboard whales, 1c auto-detect new insiders) | Polymarket Data API / on-chain |

Alongside the live copy trader, two measurement-only harnesses run in
background threads: the **copy-paper validation harness** (forward paper-copy
PnL) and **wallet discovery** (continuously hunts copyable wallets into the
paper watchlist). Neither places real orders.

## Architecture

```
poly_poly_bot/
  main.py              # Entry point — starts Strategy #1 + measurement harnesses
  src/
    config.py          # .env configuration
    config_validators.py
    models.py          # Pydantic data models
    utils.py           # Shared utilities
    logger.py          # Structured logging
    constants.py       # Contract addresses, ABIs
    copy_trading/      # Strategy 1: risk manager, order executor, trade monitor,
                       #             copy-paper harness, wallet discovery, geo scanner
    basket_arb/        # Basket-arbitrage helpers
    telegram_bot.py    # Telegram control surface
  tests/               # pytest test suite
  data/                # Runtime state (risk state, inventory, trade history)
  cache/               # API response caches
  results/             # Backtest results
  logs/                # Application logs
```

## Quick Start

### 1. Install dependencies

```bash
make setup
# or: pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your keys and strategy settings
```

### 3. Run in preview mode (recommended first)

```bash
make run-preview
# or: PREVIEW_MODE=true python main.py
```

Preview mode calculates everything, logs decisions, and sends Telegram notifications but does **not** place real orders. Simulated P&L is tracked.

### 4. Run live

```bash
make run-live
# or: PREVIEW_MODE=false python main.py
```

## Configuration

All configuration lives in `.env`. See `.env.example` for the full reference.

### Global Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PREVIEW_MODE` | `true` | `true` = dry-run, `false` = live trading |
| `PRIVATE_KEY` | | Polygon wallet private key (64 hex chars) |
| `PROXY_WALLET` | | Polymarket proxy wallet address |
| `TELEGRAM_BOT_TOKEN` | | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | | Telegram chat ID for alerts |

### Strategy 1: Copy Trading (Tiered)

- **Tier 1a** (`STRATEGY_1A_*`): Geopolitical insiders - high conviction, larger bets
- **Tier 1b** (`STRATEGY_1B_*`): Leaderboard whales - medium conviction
- **Tier 1c** (`STRATEGY_1C_*`): Auto-detected new insiders - alert-only by default

Each tier has independent: `WALLETS`, `COPY_PERCENTAGE`, `MAX_BET`, `MIN_BET`, `MAX_TOTAL_EXPOSURE`, `MAX_PRICE`, `MIN_TRADER_BET`.

## Testing

```bash
make test
# or: python -m pytest tests/ -v --tb=short

# With coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Lint
make lint
```

The test suite covers: config validators, utilities, risk managers (legacy and tiered), order verification, inventory tracking, trade store, trade queues, market price snapshots, strategy configuration, copy-paper validation, wallet discovery, and the Telegram control surface.

## Deployment

### Docker (local)

```bash
docker compose up -d
docker compose logs -f
```

### GCP Compute Engine

```bash
make deploy
# or: bash deploy.sh
```

This creates (or reuses) an `e2-small` VM in `asia-northeast1-a`, uploads the code, builds the Docker image on the VM, and starts the container with persistent volumes for data, cache, results, and logs.

## Preview Mode

Every trading function checks `PREVIEW_MODE`. When enabled:

- All signals are calculated normally
- All risk checks are evaluated
- Trade decisions are logged with full context
- Telegram notifications are sent (tagged as PREVIEW)
- Orders are **not** submitted to the CLOB
- Simulated P&L is tracked in `data/`

Always run in preview mode first to validate your configuration and observe signal quality before going live.
