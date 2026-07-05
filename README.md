# Poly Poly Bot

Automated copy-trading bot for [Polymarket](https://polymarket.com). It mirrors
the trades of vetted insider/whale wallets in real time, with tiered risk
controls, a Telegram control surface, and one-command deployment to GCP.

The bot lives in [`poly_poly_bot/`](poly_poly_bot/) — see its
[README](poly_poly_bot/README.md) for full architecture, configuration, and
testing details.

## Strategy

| Strategy | Description | Signal source |
|----------|-------------|---------------|
| **Copy Trading (tiered)** | Copies insider/whale trades — 1a geopolitical insiders, 1b leaderboard whales, 1c auto-detected new insiders | Polymarket Data API / on-chain |

Alongside the live copy trader, two measurement-only harnesses run in background
threads and never place real orders: the **copy-paper validation harness**
(forward paper-copy PnL) and **wallet discovery** (continuously hunts copyable
wallets into the paper watchlist).

## Prerequisites

- **Python 3.12+**
- **Docker** (for deployment)
- A **Telegram bot token** (from [@BotFather](https://t.me/BotFather))
- A **Polymarket wallet** (private key + proxy wallet) for live trading

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/vrnroman/pm-trader.git
cd pm-trader/poly_poly_bot

# 2. Create and fill in your environment file
cp .env.example .env
# Edit .env — at minimum set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run in preview mode (no real trades)
python main.py
```

By default `PREVIEW_MODE=true` — the bot calculates signals, logs every
decision, tracks simulated P&L, and sends Telegram notifications, but does
**not** place real orders. Always validate in preview before going live.

## Configuration

All configuration is via environment variables (`.env`). See
[`poly_poly_bot/.env.example`](poly_poly_bot/.env.example) for the full reference.

| Variable | Default | Description |
|----------|---------|-------------|
| `PREVIEW_MODE` | `true` | `true` = signals only, `false` = live trading |
| `PRIVATE_KEY` | — | Polygon wallet private key (64 hex chars) |
| `PROXY_WALLET` | — | Polymarket proxy wallet address |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | — | Telegram chat ID for notifications |

Each copy tier (`STRATEGY_1A_*`, `STRATEGY_1B_*`, `STRATEGY_1C_*`) has independent
`WALLETS`, `COPY_PERCENTAGE`, `MAX_BET`, `MIN_BET`, `MAX_TOTAL_EXPOSURE`,
`MAX_PRICE`, and `MIN_TRADER_BET`.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Bot status (balance, positions, daily limits) |
| `/pnl` | Realized + unrealized P&L |
| `/history` | Last 10 copy trades |
| `/check` | Verify trading setup (read-only, no orders) |
| `/setkey` | Rotate/clear the in-memory private key |
| `/shutdown` | Graceful shutdown (Docker restarts the container) |
| `/help` | List commands |

## Deployment (GCP)

The bot deploys to a GCP Compute Engine VM via Docker.

```bash
cd poly_poly_bot
make deploy        # or: bash deploy.sh
```

This creates (or reuses) an `e2-small` VM in `asia-northeast1-a`, builds and
pushes the Docker image, and starts the container with auto-restart and
persistent volumes for data, cache, results, and logs.

### Docker Compose (local)

```bash
cd poly_poly_bot
docker compose up --build
```

## Testing

```bash
cd poly_poly_bot
python -m pytest tests/ -q
```

## Project Structure

```
poly_poly_bot/
├── main.py             # Entry point — copy trader + measurement harnesses
├── src/
│   ├── config.py       # .env configuration
│   ├── models.py       # Pydantic data models
│   ├── logger.py       # Structured logging
│   ├── copy_trading/   # Copy trading: risk manager, order executor, trade
│   │                   #   monitor, copy-paper harness, wallet discovery
│   ├── basket_arb/     # Basket-arbitrage helpers
│   └── telegram_bot.py # Telegram control surface
├── tests/              # pytest suite
├── deploy.sh           # GCP deployment
├── Dockerfile
└── docker-compose.yml
```
