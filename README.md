# Poly Poly Bot

A **news-driven paper trader** for [Polymarket](https://polymarket.com). It reads
free news (Telegram channels, RSS, Bluesky, an X list, Tree of Alpha, Hacker
News), maps each item to a market in milliseconds, asks one bounded
`claude -p` judgement whether the item is new and material, checks on the
trade tape that the price has not moved yet, and books a $5 **paper** bet at the
real ask (fee in), sold at the real bid at +5m/+30m/+2h/+24h or held to
resolution. Control books (every material call, a tape-first book, a random
market per bet) run alongside so the result has something to beat.

Nothing here can sign an order. The copy-trading bot this repo used to run was
removed on 2026-10-27; its history is in git.

The bot lives in [`poly_poly_bot/`](poly_poly_bot/); the design is
[`src/newsbot/DESIGN.md`](poly_poly_bot/src/newsbot/DESIGN.md).

## Telegram

| Command | Shows |
|---|---|
| `/pnl` | the experiment's P&L: what the paper bets won or lost, against the controls |
| `/news` | today's funnel: read, judged, bought; which sources lead the price |
| `/status` | up? sources reading? model budget used? |
| `/help` | the list |

Any other message (a forwarded post, a link) becomes a source. A brief with a
short P&L block arrives at 08:00 UTC (16:00 SGT).

## Run and test

```bash
cd poly_poly_bot
pip install -r requirements.txt freezegun
python -m pytest tests/ -q
CLOCK_DRIFT_DAYS=90 python -m pytest tests/ -q -p tests.clock_drift_plugin
python main.py
```

Deploys go through GitHub Actions on push to `main` (test gate, image built on
the runner, pushed to Artifact Registry, pulled by the VM). See
[`.github/DEPLOY_SETUP.md`](.github/DEPLOY_SETUP.md).
