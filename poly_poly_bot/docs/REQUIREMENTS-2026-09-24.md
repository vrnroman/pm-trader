> **Status, 2026-09-26 (added by run s-wo3xsp; the owner's text below is unchanged).**
> The doc's own header says "nothing in here is implemented yet"; that was true
> on 2026-09-24. Where each part went:
>
> - Part 2 A + C and Part 1 A-D, floor $30 / daily $54: PR #41.
> - Part 2 D (flip gate, scalper rail in the form, at the door and in discovery): PR #42.
> - Part 3 R1-R3 (gate at 15 settles, three admissions every 3 h, pass/fail
>   probation), Part 2 B (proportional exits), Part 1 E (paid out today from
>   Polymarket's claims), Part 3 §3.4 forward books B150/B100 with
>   `LIVE_MIN_TRADER_BET_USD` decoupled, R4-R6: PR #44. Rounds on it: PRs #45, #46.
> - Part 3 §3.1, the owner's DECISION (Desk, 2026-09-26: yes to the doc's own
>   recommendation): the real-quote slice is the execution rail, book A the
>   fallback while the slice is thin, book A keeps running; the observer's cap
>   is an env, set Z and the near misses are quoted first, the lower books
>   feed it on a budget: this run.
> - Part 3 §3.4 item 2 (a floor per wallet chosen by the gate): the row is on
>   the Z record and the phone; real money follows it only behind
>   `LIVE_PER_WALLET_MIN_USD=true`, which ships off: this run.
> - Part 1 side observation (both containers "Up 3 minutes" at 12:53 UTC): the
>   Deploy run for f7465fe at 12:44 UTC; docker force-killed both after 10 s
>   because neither process exited on SIGTERM in time. Fixed this run (a
>   shutdown deadline in the bot, a SIGTERM handler in the sidecar).
> - Part 4 open decisions: §3.1 ruled (above); R3 numbers shipped as proposed
>   in PR #44 with the "held, not failed" deviation the owner accepted on the
>   Desk; Part 2 B/D thresholds shipped as the stated defaults; §3.4 books
>   B150 and B100 run next to B300.
>
> Numbers in the doc are the 2026-09-24 measurement; read today's from the
> commands, never from here.

# poly_poly_bot — Requirements & fix specs, 2026-09-24

Hand this whole file to an implementation session. It is self-contained: every
finding was verified on the live VM (`poly-poly-bot`, container `poly-poly-bot`)
and against Polymarket's data-api on 2026-09-24; code references are as of
commit `6531325` on `main` — re-grep before editing, other sessions are
changing the repo. Nothing in here is implemented yet. The session that wrote
this did NOT edit any source file.

Ship rules (from CLAUDE.md): full test suite + clock-drift plugin, one PR per
part is fine, deploy is automatic on push to `main`, watch the run, confirm the
container comes up.

## Contents

- **Part 1** — Daily DEAL bankroll line double-counts resolved neg-risk losers
  ($157 shown, ~$108 real) + "realized today" ignores Polymarket auto-claims +
  owner decision: floor $30, daily cap $54 (fractions to set, where the env
  lives).
- **Part 2** — The two "[LIVE] Failed" messages: SELL sized in dollars asks for
  more shares than held (CLOB 400), any target trim = full exit, exchange
  reason hidden, no FAILED row; REQUIRED flip guard (a buy the target already
  left is not traded) and a scalper rail.
- **Part 3** — Admission into set Z within ~1 week instead of weeks; what book
  A really is and the owner's DECISION on it; the $300 → $150 experiment
  (backward replay results + forward B300/B150/B100 books); the two wallets
  the owner asked about.
- **Part 4** — Priority order and the owner decisions still open.

Owner decisions already taken (2026-09-24): floor $30, daily cap $54; gate
settled count 30 → 15 but the +10% ROI floor STAYS; a flip
the target has already exited must be detected and NOT traded; B300 keeps
running unchanged while lower-threshold books are added.

---

# PART 1 — The daily DEAL line overstates the bankroll (dead neg-risk losers counted at cost) + owner's floor $30 / daily $54

Written 2026-09-24 by a session that only investigated. Nothing below is
implemented. Line numbers are as of commit `6531325` (main, 2026-09-24);
re-grep before editing, another session is changing the repo.

### What the owner saw

08:00 UTC DEAL message:

```
💵 real money: bankroll $157.00 (USDC $108.15 + open at cost $48.85) · floor $56 · distance $+101.00 · realized today $+0.00 (0 redeem(s))
```

### What was true at 08:00 UTC (verified on chain + Polymarket data-api)

| figure | line said | truth |
|---|---|---|
| pUSD cash on chain (`0xC011a7E1…`) | $108.15 | $108.15 (correct) |
| open positions at cost | $48.85 | $0.00 (the three overnight bets had all won and been auto-claimed by 05:35 UTC) |
| bankroll (equity) | $157.00 | $108.15 |
| distance to $56 floor | +$101 | +$52 |
| realized today | $0.00, 0 redeems | 3 payouts, $42.24 (Comesana $20.00, Ma/Birrell $9.69, Diamondbacks under $12.55) |

The $48.85 is EXACTLY the sum of 8 resolved, worthless, neg-risk positions
still sitting in `data/inventory.json` at cost:

| market | cost |
|---|---|
| Will Cruzeiro EC win on 2026-09-06? No | 5.50 |
| Will Incheon United FC win on 2026-09-08? No | 5.98 |
| Palermo FC leading at halftime? No | 6.40 |
| El Qanah vs Tala'ea El Gaish draw? No | 6.40 |
| Alanyaspor vs Göztepe draw? No | 5.37 |
| Will Deportivo Toluca FC win on 2026-09-20? Yes | 6.40 |
| Bayern vs Man City WFC draw? No | 6.40 |
| Will Spain win on 2026-09-23? No | 6.40 |
| **total** | **48.85** |

Reproduced on the VM at 12:54 UTC inside the bot container:

```
[guard] 8 neg-risk position(s) excluded: the redeemer skips them by design
inventory rows 77  total cost 673.98  redeemable rows 67
live_open_cost -> (61.65, 67, True)      # 48.85 dead + 12.80 truly open (Dallas temp, Mertens spread)
```

### Root cause

One list serves two different questions.

1. `src/copy_trading/live_guard.py:185` `redeemable_positions()` fetches the
   data-api positions with `redeemable == True` (via
   `auto_redeemer._fetch_redeemable_positions`) and then DROPS neg-risk rows
   (`_is_neg_risk`, key `negativeRisk`). That filter is correct for its
   original purpose: the redeemer skips neg-risk by design, so counting them
   as "stuck, unredeemed" would self-disarm the session
   (`tests/test_zset_and_guard.py::test_neg_risk_positions_do_not_disarm_the_session`).

2. `src/copy_trading/live_budget.py:287` `live_open_cost(summary, redeemable)`
   treats every token id in that list as "resolved, not worth its cost" and
   counts everything ELSE in the inventory at cost. Because neg-risk rows were
   filtered out upstream, every resolved neg-risk LOSER stays in the "live"
   set forever and is counted at what we paid.

3. `inventory.sync_inventory_from_api` keeps those rows because the data-api
   still lists them (size > 0, currentValue 0) and nobody redeems a $0 token,
   so they never age out. The set grows by one ticket per lost neg-risk bet.

Two call sites feed this inflated open-cost into money decisions:

- `main.py:199` + `main.py:246` (guard thread, every ~300s): the FLOOR
  trigger's equity (`equity_usd`, passed to `live_guard.run_once` at
  `main.py:325`) and the sizing cache (`live_budget.note_open_cost` at
  ~`main.py:262`, which `caps()` reads at `live_budget.py:217`). The floor
  cannot fire on time; per-copy sizing is computed off phantom equity.
- `src/copy_trading/rehearsal.py:370` + `:373` (`real_money_line`, the 08:00
  DEAL line and anything else rendering it).

### The fix

#### A. Split the two questions in `live_guard.py`

```python
def resolved_positions(proxy_wallet: str) -> Optional[list]:
    """EVERY position the data-api marks redeemable, neg-risk included.
    This is the 'no longer worth its cost' set for equity. None on a failed
    read (not [] — the callers treat None as unknown)."""
    # body = current redeemable_positions() minus the neg-risk filter

def without_neg_risk(rows: Optional[list]) -> Optional[list]:
    """The redeemer's view: rows it will actually try to redeem. The stuck-
    redemption trigger must use THIS, never the full set."""
    if rows is None:
        return None
    kept = [p for p in rows if not _is_neg_risk(p)]
    # keep the existing "N neg-risk position(s) excluded" log line here
    return kept

def redeemable_positions(proxy_wallet: str) -> Optional[list]:
    return without_neg_risk(resolved_positions(proxy_wallet))
```

Keep `redeemable_positions` so existing tests and callers still work.
Fix its docstring/return annotation while there: it already returns `None`
on failure (line 217) but is annotated `-> list`.

#### B. `main.py` guard loop (one fetch, two views)

Around line 199:

```python
resolved = live_guard.resolved_positions(CONFIG.proxy_wallet)   # full set, for equity
redeemable = live_guard.without_neg_risk(resolved)              # redeemer's set, for the stuck trigger
```

Then at line 246 pass `resolved` (not `redeemable`) into
`live_budget.live_open_cost(...)`. Leave `run_once(redeemable=redeemable, ...)`
and the `_winners`/`note_collectable` block on `redeemable` as they are: the
redeemer really will not collect neg-risk winners, so they are not
"collectable" — but they ARE worth their `currentValue`, so for
`note_open_cost(open_cost + _resolved)` compute `_resolved` over the FULL
`resolved` list, not `redeemable` (a neg-risk winner's payout is real equity
even if our redeemer will not be the one to claim it; Polymarket auto-claims).

#### C. `rehearsal.py::real_money_line` (line ~370)

```python
redeemable = live_guard.resolved_positions(CONFIG.proxy_wallet)
```

`resolved_positions_line(redeemable, n_done)` below it should keep working
unchanged (it sums `_position_value`, which is 0 for the losers).

#### D. Do NOT touch `live_budget.live_open_cost`

Its logic is right; it was handed the wrong list. Its docstring already
describes the failure this is ("61 resolved losers … made the bankroll read
far above the floor") — that fix just missed the neg-risk hole.

#### E. "realized today" should see Polymarket's own claims (same message, second bug)

`rehearsal.py:377` sums only `realized-pnl.jsonl` rows with
`source == "redeemer"`. Polymarket auto-claims wins hours before our redeemer
sees them (three today, $42.24, before 05:35 UTC), and the redeemer then
reports "each worth under $1: nothing to claim, nothing sent, no P&L
recorded". So on a winning day the line says `$+0.00 (0 redeem(s))`.
Known since 09-16 (memory `external-redeem-unbooked`, PR #38 rebuilt `/real`
on Polymarket data); the daily line was never switched.

Minimal change: read today's REDEEM rows from the data-api like `/real`
does, and render BOTH numbers so nothing is over-claimed:

```python
from src.copy_trading import real_money
day0 = <00:00 UTC of today as int ts>
rows = real_money.fetch_activity(CONFIG.proxy_wallet, since_ts=day0)   # None on failure
deals, _ = real_money.parse_deals(rows or [], since_ts=day0)
payouts = [d for d in deals if d.kind == real_money.PAYOUT]
paid_out = round(sum(d.usd for d in payouts), 2)
```

Render as e.g.
`· paid out today $+42.24 (3 claim(s), Polymarket's own) · realized by the bot $+0.00 (0 redeem(s))`.
If `rows is None`, say `paid out today: could not read` rather than $0.
Gross payout is not P&L; if the fix wants P&L per claim, `real_money.build_book`
already matches buys to payouts per market (`MarketResult.paid_usd`,
`paid_out_usd`), restrict to markets whose payout ts is today.

Update `tests/test_golive_month_one.py::test_real_money_line_counts_only_redeemer_rows`
(line 816) to the new wording; it currently asserts the redeemer-only
behaviour that IS the bug.

### Tests to add

1. `live_open_cost` given the FULL resolved set excludes a neg-risk loser:
   inventory holds token T (neg-risk, resolved, cost 6.40) and token U (open,
   cost 6.40); resolved set = [T with negativeRisk=True, currentValue 0];
   expect `(6.40, 1, True)`. Under the current wiring
   (`redeemable_positions` output) the answer is `(12.80, 0, True)`; the test
   should exercise the main.py / rehearsal wiring, not just the pure
   function, otherwise it passes today.
2. The guard's stuck-redemption trigger STILL ignores neg-risk rows
   (existing `test_neg_risk_positions_do_not_disarm_the_session` must stay
   green with the new `without_neg_risk`).
3. The 08:00 line: with cash 108.15, the 8 neg-risk losers above in the
   inventory, and the data-api rows marking them redeemable, the line renders
   `bankroll $108.15 (USDC $108.15 + open at cost $0.00)` and
   `distance $+52.15`.
4. `real_money_line` with a mocked `fetch_activity` returning three REDEEM
   rows today renders `paid out today $+42.24 (3 claim(s)…)`; with
   `fetch_activity` returning None it renders "could not read", never $0.

Run the full suite plus the clock-drift plugin per CLAUDE.md before pushing.

### Verification on the VM after deploy

Inside the bot container (`sudo docker exec poly-poly-bot python3 -c ...`):

```python
from src.copy_trading import inventory, live_guard, live_budget
from src.config import CONFIG
s = inventory.get_inventory_summary()
r = live_guard.resolved_positions(CONFIG.proxy_wallet)
print(live_budget.live_open_cost(s, r))   # expect (~12.80 or whatever is truly open, 75, True)
```

Then trigger the daily line (or wait for 08:00 UTC) and check the bankroll
equals `pUSD on chain + cost of positions the Polymarket UI shows as open`.
Chain read that works from a laptop (polygon-rpc.com answers 401 now):

```
rpc https://polygon-bor-rpc.publicnode.com, ERC20 balanceOf on 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB
```

### Side observation (not part of this fix)

Both containers (`poly-poly-bot`, `poly-poly-sre`) showed "Up 3 minutes" at
12:53 UTC on 2026-09-24. Something restarted them around 12:50 UTC; not
investigated.

### Owner decision (2026-09-24): floor $30, daily limit $54

Both numbers are derived from `LIVE_BUDGET_USD=80` by fractions in
`src/copy_trading/live_budget.py`; there is no absolute knob today.

| figure | now | formula | wanted | fraction to set |
|---|---|---|---|---|
| floor (bankroll below which the guard disarms) | $56 | `80 × (1 − LIVE_BUDGET_DRAWDOWN_FRAC)`, frac 0.30 | **$30** | `LIVE_BUDGET_DRAWDOWN_FRAC=0.625` |
| daily cap (`caps().daily_usd`, clamps the tier's daily volume) | $32 | `80 × LIVE_BUDGET_DAILY_FRAC`, frac 0.40 | **$54** | `LIVE_BUDGET_DAILY_FRAC=0.675` |

Verified on the VM 2026-09-24: the container runs with
`LIVE_BUDGET_USD=80 LIVE_BUDGET_PER_COPY_FRAC=0.08 LIVE_BUDGET_DAILY_FRAC=0.40
LIVE_BUDGET_EXPOSURE_FRAC=0.80 LIVE_BUDGET_DRAWDOWN_FRAC=0.30`, and
`caps(live=True)` prints `daily_usd=32.0`, `floor_usd()` prints `56.0`.
`_frac()` accepts anything in `(0, 1]`, so 0.625 and 0.675 are valid.

Where to change it (BOTH, or the next deploy reverts it):

1. The GitHub secret `ENV_FILE` (repo Settings > Secrets). The `Deploy`
   workflow regenerates the VM's `~/app/.env` from it on every push to main
   (`.github/workflows/deploy.yml:68-80`, `:149`). Change the two lines there.
2. The running VM, without waiting for a deploy: edit `~/app/.env` on the VM
   (same two lines) and recreate the container so `--env-file` is re-read
   (a `docker restart` does NOT re-read the env file; use the deploy's
   `docker run` block in `deploy.sh:223`, or just push a commit and let the
   workflow do it).

Note the local `poly_poly_bot/.env` on the Mac carries none of the
`LIVE_BUDGET_*` lines; it is NOT what the VM runs. Do not "fix" it by copying.

Consider, while there: an absolute override (`LIVE_FLOOR_USD`,
`LIVE_DAILY_USD`) taking precedence over the fractions, so the owner states
dollars instead of solving for a fraction each time the budget moves. The
floor's docstring (`live_budget.py:60-65`) says the fixed floor should fire
on "roughly eight to twelve net losing tickets"; at $6.40 tickets, $30 under
$80 is ~8 losing tickets, consistent with that intent. The daily cap $54
allows ~8 tickets a day.

After the change the DEAL line should read `floor $30` and `/live` (or the
governor panel) `daily $54`. With today's true bankroll (~$108) the distance
to the floor is ~$78.


---

# PART 2 — "[LIVE] Failed … Order placement returned no result": mirrored exits oversized, dust trims, opaque failures, and the un-copyable flip rule

Written 2026-09-24 by a session that only investigated. Nothing below is
implemented. Line numbers are as of commit `6531325` (main); re-grep first,
another session is changing the repo.

### What the owner saw

```
[💰 DEAL] 🔴 [LIVE] Failed
"Buenos Aires 2: Francisco Comesana vs Joaquin Aguilar"
Order placement returned no result
```

### What actually happened (VM logs `/app/logs/bot-2026-09-23.log`, data-api)

Both live "Failed" messages of 2026-09-23 are the same defect. The CLOB's
real answer is in the log but never reaches the phone:

```
2026-09-23 23:18:14 [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/order
  body={"error":"not enough balance / allowance: the balance is not enough -> balance: 20000000, order amount: 20830000"}
2026-09-23 23:18:14 ERROR [exec] Order placement failed: PolyApiException[status_code=400, ...]
2026-09-23 23:18:14 ERROR [exec] Order placement returned None for 'Buenos Aires 2: Francisco Comesana vs Jo'
```

`balance` / `order amount` are in 6-decimal token units: we held **20.00
shares** of Aguilar and posted a **SELL of 20.83 shares**. Same on Spain:

```
2026-09-23 07:49:57 TRADE [verify] FILLED: BUY 22.86 shares on 'Will Spain win on 2026-09-23?' @ 0.2800
2026-09-23 07:49:59 ... balance: 22860000, order amount: 23700000      <- SELL 23.70, held 22.86
```

#### Timeline, Comesana vs Aguilar (followed wallet `0x9f15…bdb3`, tier 1b)

| UTC | followed wallet | bot |
|---|---|---|
| 21:53:58 | BUY 982 sh Aguilar @0.31 ($304.50) | copied: BUY $6.40 → 20.00 sh @0.32, FILLED |
| 22:57:29 | BUY 1887 sh @0.27 ($509.51) | skipped, daily cap $32 reached |
| 23:03:05 | BUY 3.34 sh @0.27 ($0.90) | skipped, under min trader bet |
| 23:17:37 | **SELL 3.34 sh @0.24 ($0.77)**, a 0.1% trim of their ~2,870 sh | mirrored as a FULL exit: $6.40 ÷ bid ≈0.307 = **20.83 sh** > 20.00 held → CLOB 400 → "Failed" |
| 05:35 next day | | position won, Polymarket auto-claimed $20.00 |

Had the sell been accepted, the bot would have dumped its entire winning
position at ~0.24-0.31 because the target trimmed a tenth of a percent.

#### Timeline, Spain No (same wallet)

| UTC | followed wallet | bot |
|---|---|---|
| 07:49:28 | BUY 1121.34 sh No @0.28 ($313.98) | copied: BUY $6.40 → 22.86 sh @0.28, FILLED 07:49:57 |
| 07:49:29 | **SELL 1121.33 sh @0.2704** (a 1-second flip, −$22 for them) | mirrored at 07:49:59: $6.40 ÷ bid 0.27 = **23.70 sh** > 22.86 held → CLOB 400 → "Failed" |
| later | | Spain won; our No lost the full $6.40. Their exit would have returned ~$6.17. |

### Root cause (three parts)

1. **A SELL is sized in dollars, never in shares held.**
   `tiered_risk_manager._evaluate_tiered_trade_with_state` (~line 240):
   `size = max(trade.size × copy_percentage, cfg.min_bet)` then
   `min(size, max_bet)`; under the governor min_bet = max_bet = per-copy cap
   ($6.40 = 80 × `LIVE_BUDGET_PER_COPY_FRAC` 0.08). Then
   `trade_executor._execute_copy_order` (line ~313):
   `shares = shares_for(copy_size, order_price)` with `order_price` = best
   bid for a SELL. Whenever the bid is at or below our entry (exactly when an
   exit matters), `$6.40 / bid` > shares we bought for $6.40, and the CLOB
   rejects the whole order. The "exit clamp" shipped 09-13 clamps only the
   PREVIEW booking (`_book_preview_exit`, `qty = min(sell_shares, held)`,
   line 261); the live order is never clamped.

2. **Every mirrored exit is all-or-nothing at the minimum ticket.** The
   min-trader-bet gate is deliberately BUY-only (comment at ~line 222,
   "mirrors exits from $100"), and `min_bet` floors the size, so a $0.77
   trim by the target becomes a $6.40 (i.e. full-position) exit by us. Book
   B's evidence was "mirror their exits", not "exit fully on any sell".

3. **The failure is opaque and unrecorded.** `trade_executor.py:883-895`:
   on `result is None` the bot sends `tg.trade_failed(market, "Order
   placement returned no result")` and writes NO trade-history row; the
   CLOB's reason lives only in the log. Every distinct failure (bad price,
   zero shares, no order id, any exception) collapses into one sentence.

### The fix

#### A. Size a live SELL in shares, from what we hold (`trade_executor.py`)

In `_execute_copy_order` (or just before calling it, where `copy_size` is
final), for `trade.side == "SELL"`:

```python
held = inventory.get_position(trade.token_id)          # {"shares", "avg_price", ...}
held_sh = float((held or {}).get("shares") or 0.0)
if held_sh <= 0:
    skip("SELL: no shares held")                        # existing has_position check covers most of this
# fraction of THEIR position they just sold; see B for where trader_position comes from
frac = min(1.0, trade.size_shares / trader_position_shares_before) if trader_position_shares_before else 1.0
shares = round(min(held_sh, held_sh * frac), 2)
```

and post `OrderArgs(size=shares, ...)` directly, never `copy_size / price`.
Keep `copy_size` (dollars) only for ledgers/notifications, computed as
`shares × order_price`.

Hard rule regardless of B: **`size` on a live SELL ≤ shares held, always.**
If the CLOB's minimum order size makes a proportional sell too small, sell
the CLOB minimum or skip with a reason; never round UP past `held_sh`.

Note `record_sell(token_id, shares)` after a fill must use the FILLED
shares, and `inventory.sync_inventory_from_api` will reconcile anyway.

#### B. Mirror exits proportionally, ignore dust trims (`tiered_risk_manager.py`)

Need the target's position size before the sell. Options, cheapest first:

- The trade row from the data-api / chain reader carries `size` (shares). The
  bot already tracks the wallet's activity; keep a running per-wallet,
  per-token share count in `trade_store` (buys add, sells subtract), or read
  `/positions?user=<wallet>` once per SELL (one call, cached 60 s).
- Rule: `frac = their_sold_shares / their_shares_before`.
  - `frac < 0.10` (a trim): skip, reason `"target trimmed {frac:.1%}: not an exit"`.
  - `0.10 ≤ frac < 0.90`: sell `held × frac` (subject to the CLOB minimum).
  - `frac ≥ 0.90`: sell everything we hold.
- Thresholds are stated defaults, not measured; expose as
  `COPY_EXIT_TRIM_FRAC` / `COPY_EXIT_FULL_FRAC` env and note them in
  `.env.example`.

The min-trader-bet exemption for SELLs stays; it is correct.

#### C. Say what the exchange said (`trade_executor.py:883-895`, `telegram_notifier.trade_failed`)

- Make `_execute_copy_order` return a reason with the None (e.g. return
  `(None, why)` or raise a typed `OrderRejected(why)` caught at the call
  site). Carry the CLOB body through.
- Telegram text, e.g.:
  `🔴 [LIVE] SELL not placed "Comesana vs Aguilar": exchange refused — we hold 20.00 shares, the order asked for 20.83 (target sold 0.1% of theirs)`.
- Write a `TradeRecord(status="FAILED", reason=why, copy_size=..., ...)`
  row so `/pnl`, `/real` and the audit trail see it. Today there is no row at
  all for either failure.
- Keep the daily-cap "reservation kept" behaviour for BUYs (its comment is
  right: None can be a timeout after acceptance). For a **400 from the CLOB
  the order was definitely NOT accepted**, so the reservation can be released
  on a SELL/400; leave BUY/timeout ambiguous as it is.

#### D. REQUIRED (owner decision 2026-09-24): a flip the target has already left is not traded

The Spain trade was a buy and a full sell 1 second apart by the target. With
~30 s copy latency (data-api lag, memory `telegram-follow-and-latency`) the
bot bought into a position the target had already left, then could not
follow them out, and ate the full loss. The owner's rule: **such a trade is
detected and refused, never copied.** Two layers, both required.

**D1. Per-trade: "has the target already exited this?" gate, before any BUY posts.**

Place it in `trade_executor` right before the governor/cash checks (~line
744), after the market-quality check, so it runs only on trades that would
otherwise post. Also run it in the preview path so the paper books stop
crediting flips that live money could never take.

```python
def target_already_exited(trader_address, token_id, buy_ts, buy_shares) -> tuple[bool, str]:
    """Did the target SELL this token after the buy we are about to copy?"""
    # 1. local first: trade_store already holds every row the pollers fetched
    #    for this wallet (fast Z poll + data-api poll); scan rows with the same
    #    token_id, side SELL, timestamp >= buy_ts.
    # 2. if the store has nothing newer than buy_ts for this wallet at all,
    #    one data-api call: /activity?user=<trader>&limit=50 (cache 30 s per wallet)
    sold = sum(size of those SELL rows)
    frac = sold / buy_shares
    if frac >= COPY_FLIP_EXIT_FRAC:          # default 0.5
        return True, f"target already sold {frac:.0%} of this buy {age}s later"
    return False, ""
```

Skip with `_skip_row(...)` and the reason above (status SKIPPED, so
`/pnl`, `/real` and the trade history show why). Env
`COPY_FLIP_EXIT_FRAC` (default 0.5), documented in `.env.example`.

Detection latency makes this check cheap and reliable: by the time the bot
sees the buy (~30 s), a 1-second flip's sell is already in the same activity
page. It also covers a sell that lands while the trade sits in the retry
queue.

**D2. Per-wallet: scalpers are not copyable at our latency.**

A wallet whose exits routinely follow its entries within minutes has no
copyable edge at 30 s latency, whatever its ROI. Add a hold-time
characteristic to the wallet screen (discovery + `wallet_form`, wherever the
form/quality rails read a wallet's activity):

- `median_hold_s` and `flip_frac` = share of round-trips (buy then sell of
  the same token) closed within `COPY_FLIP_WINDOW_S` (default 600 s).
- Refuse admission to Z, and bench a Z wallet, when `flip_frac >
  COPY_FLIP_MAX_FRAC` (default 0.20) over the form window. Reason text:
  `"scalper: {flip_frac:.0%} of exits within 10 min; uncopyable at our latency"`.
- Render it in the wallet dossier / `/wallets` row so the owner sees WHY.

Thresholds are stated defaults, not measured; the replay data in the paper
books (`copy_paper_ledger*.jsonl`) can calibrate them: compute, per wallet,
the ROI of buys whose target exit came within 10 min versus the rest.

**D3. What NOT to do:** do not "exit immediately at market when we notice
the target left" as the primary fix. That still pays the spread twice on a
trade with no edge; the owner wants it not traded. An immediate exit remains
a reasonable fallback only for the race window (target exits AFTER our post
but before our fill), and even then A/B sizing rules apply (never above
held).

### Tests to add

1. Live SELL with held 22.86 sh, bid 0.27, copy_size $6.40: the posted
   `OrderArgs.size` is ≤ 22.86 (regression for the CLOB 400).
2. Target sells 0.1% of their position: no order posted, skip reason names
   the trim.
3. Target sells 100%: the bot sells all held shares.
4. Target sells 50%: the bot sells half, rounded to 2 dp, never above held.
5. CLOB rejects with a 400 body: the Telegram text contains the exchange's
   reason and the held/asked shares; a FAILED row is written to
   `trade-history.jsonl`.
6. Existing: `_book_preview_exit` clamp test stays green; preview path
   unchanged.
7. Flip gate (D1): a queued BUY whose target SOLD 100% of it 1 s later (both
   rows in trade_store) → not posted, SKIPPED row with reason "target already
   sold 100%"; sold 30% → posted (under the 0.5 default); store empty but the
   data-api page shows the sell → not posted (fallback fetch works and is
   cached).
8. Scalper rail (D2): a wallet with 3 of 10 round-trips under 10 min is
   refused admission / benched with the scalper reason; 1 of 10 passes.

Run the full suite and the clock-drift plugin per CLAUDE.md before pushing.

### Verify on the VM after deploy

```
sudo docker exec poly-poly-bot grep -c "not enough balance" /app/logs/bot-$(date -u +%F).log   # expect 0 over a day
sudo docker exec poly-poly-bot grep "FAILED" /app/data/trade-history.jsonl | tail            # failures now carry a reason
```

and the next mirrored exit should appear in the signals log as
`TRADE [LIVE] SELL <n> shares (their exit x%)` with n ≤ held.


---

# PART 3 — Promotion into set Z within ~1 week, book A's role, and the $300 → $150 question

Investigated 2026-09-24 on the VM (live ledgers) and in the code at `6531325`.
Nothing implemented. Owner decisions are marked **DECISION**.

## 3.1 What books A and B actually are (read the code, not the memory)

Both paper books run the same engine (`copy_paper.CopyPaperEngine`,
`copy_paper_runner.CopyPaperRunner`); one argument sets the fill regime.

| | Book A (`main.py:432-737`) | Book B (`main.py:839-1098`) | Live orders (`order_executor.quote_copy_order`) |
|---|---|---|---|
| Entry price | walks the REAL order-book asks at cycle time (after our detection lag); drops the fill if the average is >150 bps from their price (`COPY_PAPER_FILL_GATE_BPS`) | target's own price × 1.01 (`COPY_PAPER_B_SLIPPAGE_BPS`=100), no book read, no gate | best ask at post time; refused if mid drifted >300 bps or spread >500 bps |
| Exit (target sells) | at OUR best bid, clamped to their exit if >500 bps away | at THEIR exit price | mirrored at best bid (and today oversized, see Part 2) |
| Per-wallet pace | 3 copies/day (`COPY_PAPER_MAX_PER_WALLET_DAY`) | 25/day (`COPY_PAPER_B_MAX_PER_WALLET_DAY`) | 2/day (`LIVE_MAX_PER_WALLET_DAY`), probation 1/day |
| Min target bet | `COPY_PAPER_MIN_USD`=300, shared | same | same variable, via `live_budget.caps().min_trader_bet_usd` |

So **A is not "the same as B with delayed bets" — A is what OUR money gets**
(we ARE the delayed copier: p50 18 s on data-api, up to 8 min on weather
wallets). B is the zero-latency best case. When memory says "book B negative
at real quotes, profit sits in mirrored exits", that is exactly the gap
between B and A/live. Deleting A would leave the gate with only the
optimistic book.

The 40-of-149 wallets that the "A does not contradict" rail rejects are
wallets whose copies, at the prices we would really pay, lose money.

**DECISION (owner):** what to do with A in the gate. Options, with my
recommendation first:

1. **(recommended) Replace the A rail with the real-quote slice as the rail.**
   `zset_candidates.real_quote_slice` already re-prices each B copy at the
   `our_price` the shadow observer captured with the SAME `quote_copy_order`
   live uses (`shadow-quotes.jsonl`). It is per-copy, more precise than A's
   thin 3/day sample, and today it is display-only. Rule: `real_roi ≥ 0`
   over ≥15 matched copies; when the slice is thin (<15 matched) fall back to
   the A rail as it is now. Keep A running (it costs nothing) but stop
   gating on it once the slice covers the wallet.
2. Keep A as the rail (status quo). Cheapest; rejects ~27% of otherwise
   eligible wallets, some on thin samples (A n=10-19).
3. Drop A from the gate entirely and delete book A. **Not recommended**:
   the gate would then be blind to execution cost, which is the one thing
   that has actually hurt real money so far.

Whatever is chosen, fix the shadow observer's coverage so the slice is not
thin: it quotes at most 40 detected trades per sweep and drops the overflow
(`shadow_quote.py`), and excludes rows quoted >30 s after detection. Raise the
cap (env) and quote set-Z / near-miss wallets first.

## 3.2 Why promotion takes weeks today — measured on the live B ledger (2026-09-24)

| measure | value |
|---|---|
| wallets with any B copy / rows | 466 / 7,492 (7,265 in the clean era since 2026-07-25) |
| B opens per wallet per week (last 14 d) | median 0, p75 0.5, p90 4, max 63 |
| wallets making ≥30 / ≥15 / ≥5 opens a week | 4 / 11 / 42 |
| wallets with ≥30 clean settles / 15-29 / 5-14 / <5 | 48 / 97 / 111 / 210 |
| days from first clean open to 30th settle (the 48 that got there) | median 14, p25 11, min 1, p75 32 |
| hours from open to settle | median 3 h, p75 5 h, p90 15 h |
| gate today: passers / near-misses (≤2 fails) | 15 (all already in Z; Z has 17) / 12 |

Fail counts among the 149 wallets with ≥15 settled copies (a wallet can fail several):

| check | wallets failing |
|---|---|
| still positive with best 3 copies deleted (concentration) | 114 |
| promotion floor ROI ≥ +10% | 112 |
| ≥30 settled (all-time / clean era) | 101 |
| paper ROI ≥ 0 | 79 |
| under an auto-demote (A or B blacklist) | 79 |
| at-their-price ROI ≥ 0 | 76 |
| active within 14 d | 69 |
| book A does not contradict | 40 |

Reading: **the count is not the main brake for active wallets** (median 14
days to 30 settles, markets settle in ~3 h). The brake is (a) most wallets
place few ≥$300 bets, and (b) the ROI floor and the concentration rail, which
are the checks that say "the edge is real", not "wait longer".

For scale, a rule of ≥15 clean settles and paper ROI ≥ +5% (trimmed ≥ 0,
at-their-price ≥ 0, no A rail) would admit **25 wallets vs 15 now** — the
owner kept the +10% floor, so the operative number is the 22 in R1 below.
The 10 new ones: 0x141a5834 (A −38% over 12: the A rail's point),
0xff7ca9cd (+5%, trimmed +1%), 0x10658d37 (+35%, trimmed +2%), 0xa42f3648
(+40%, n=19), 0x3968f7c9 (+45%, n=17), 0xf7eb35cd (+38%, n=16), 0x91c7d990
(+13%, n=17), 0x984ffef1 (+33%, n=29), 0x19585131 (+35%, n=19), and
0x57b25849 (+7%; already in Z from an earlier era).

## 3.3 Requirements: admission in ~1 week

The principle: **admit faster, but let probation be the real test with real
money capped**, instead of asking the paper book to prove everything first.

**R1. Gate thresholds (env, defaults change) — OWNER DECIDED 2026-09-24:**
- `COPY_GOLIVE_MIN_SETTLED` 30 → **15**, `COPY_GOLIVE_MIN_CLEAN_SETTLED` 30 → **15**. (Agreed.)
- `COPY_PROMOTE_MIN_ROI` **stays +10%**. (Owner rejected lowering it to +5%.)
- Keep: trimmed (best-3-deleted) ≥ 0, at-their-price ≥ 0 over ≥5, active
  within 14 d, split-half book persistence.
- A rail: per DECISION in 3.1.
- Expected effect today (n ≥ 15, ROI ≥ +10%, trimmed ≥ 0, ideal ≥ 0, A rail
  kept): 15 → **22 passers**. The 7 new ones, all with 15-29 settles and ROI
  well above the floor: 0x10658d37 (+35%, n=23), 0xa42f3648 (+40%, n=19),
  0x3968f7c9 (+45%, n=17), 0xf7eb35cd (+38%, n=16), 0x91c7d990 (+13%, n=17),
  0x984ffef1 (+33%, n=29), 0x19585131 (+35%, n=19). The three that only the
  +5% floor would have let in (0x141a5834 +8%, 0xff7ca9cd +5%, 0x57b25849
  +7%) stay out.

**R2. Admission cadence:** `ops_admit.scan(limit=1)` is hard-coded to one
wallet per 6-hour scan (`ops_admit.py:21`, `main.py:171`). Add
`ZSET_AUTO_ADMIT_LIMIT` (default **3**) and set `ZSET_AUTO_ADMIT_EVERY_S` to
**10800** (3 h). Ten eligible wallets then enter within a day, not a week.

**R3. Probation becomes pass/fail.** Today probation ends after 5 live
settles "whatever the result" (`ops_watch.py:618-635`). Requirement:
- length: `ZSET_PROBATION_SETTLED_N` = 5 live settles (keep) OR 10 calendar
  days, whichever first;
- pass: ≥2 of 5 won AND at-their-price ROI of the live copies ≥ −10%;
- fail → auto-evict with the numbers in the Telegram line (Evict is
  reversible via `/zset readmit`);
- probation caps stay (1 copy/day/wallet, 2/day across probationers) — raise
  `ZSET_PROBATION_TOTAL_PER_DAY` to **4** if R2 admits more wallets, else
  probationers queue behind each other and the 10-day clock runs out.

**R4. Make "active within 14 d" read the wallet's own trades**, not our
copies. 69 wallets fail it; several are active but produce no ≥$300 bets or
hit the per-day/category caps. `wallet_form` already fetches the wallet's
own activity every 6 h; reuse its `last_trade_ts`.

**R5. Align discovery with B.** Discovery's copy-replay scores wallets at
`DiscoveryConfig.min_usd` = **$500** (`discovery.py:41`) while B copies at
$300: the watchlist is chosen on a different population of bets than the
one B (and Z) then trades. Set discovery's replay `min_usd` from the same
env as the book it feeds.

**R6. Surface the blockers.** `/wallets` and the daily digest should show,
per near-miss wallet, the failing checks with numbers (the gate already
returns them; today only the card in `/zset candidates` renders them).

## 3.4 The $300 → $150 experiment

### Backward test (can be done from data already on the VM)

`data/wcache/<wallet>.json` holds each watched wallet's raw activity (up to
4,000 events, refreshed every 30 h) and `data/rescache/res_<conditionId>.json`
the winning outcome. The bot's own replay engine `copy_replay.score_copy_replay(buys,
round_trips, min_usd=…, first_entry_only=True)` is pure and takes `min_usd`,
so it can be run offline at 300 / 200 / 150 / 100 for every wallet (via
`wallet_context.build_context(wallet, acts, resolutions=…)` with
`market_resolution._read_cache` so nothing hits the network).

What it measures: copy-and-hold at the wallet's own price, first entry per
market, ROI = 1/price − 1 on a win, −1 on a loss. What it misses: mirrored
exits (where B's realized profit mostly sits), execution drag, and history
beyond 4,000 events for heavy traders.

**Result (run 2026-09-24 on the VM, clean era since 2026-07-25, 966 watched
wallets):**

Method as above but re-implemented in a 60-line script (`/tmp/th2.py` on the
VM, 1,012 s): every wallet on the watchlist, B extras or B ledger (780; **255
had no `wcache` file** — the cache is pruned after 30 h and Z/B-extras wallets
are not always in discovery's set, so several current Z members are missing
from this table), BUY rows since the era floor, first entry per market,
resolved via `rescache`, ROI at their price held to resolution. "Strict" =
today's bar (n ≥ 30, ROI ≥ +10%, trimmed ≥ 0); "relaxed" = n ≥ 15, ROI ≥ +5%,
trimmed ≥ 0 — shown for scale only, the owner kept the +10% floor (R1's bar
is n ≥ 15, ROI ≥ +10%, which sits between the two columns). PnL = Σ n × ROI × $6.40 (one live ticket per copy).

| min bet | wallets with ≥1 resolved copy | copies | ROI per copy | PnL @ $6.40 all | strict passers (their PnL) | relaxed passers (their PnL) | wallets ≥15 copies/week |
|---|---|---|---|---|---|---|---|
| **$300 (today)** | 351 | 19,687 | +5.6% | $7,072 | 42 ($4,797) | 72 ($7,049) | 62 |
| $200 | 419 | 28,692 | +5.3% | $9,746 | 58 ($8,066) | 99 ($10,847) | 99 |
| **$150** | 456 | 36,715 | +5.1% | $11,895 | 64 ($10,051) | 110 ($13,116) | 121 |
| $100 | 493 | 58,472 | +4.5% | $16,828 | 82 ($12,911) | 138 ($18,764) | 189 |

Reading:
- **Per-copy edge barely moves** ($300 +5.6% → $150 +5.1% → $100 +4.5%): the
  $150-300 bets of these wallets are about as good as their $300+ bets.
- **Evidence arrives ~2× faster at $150** (36.7k vs 19.7k copies; wallets able
  to produce 15 copies a week: 62 → 121). That is the lever for "a week, not
  a month".
- **The set of good wallets changes, not just its size.** At $150: 33
  wallets pass the strict bar that do not at $300, and **11 pass at $300 but
  fail at $150**, i.e. their smaller bets lose: `0x145a5b44` (+18% at $300 →
  −1% at $150), `0x59e2375d` (+13% → −1%), `0x5e517510` (+12% → +6%,
  trimmed +2%), `0x722abb54` (**in Z today**, +10% → +2%, trimmed −1%),
  `0x8ec422e3`, `0x8f88b822`, `0xa16b4c92`, `0xa538af77`, `0xae2b654c`,
  `0xd47e7b93`, `0xdcb848cd`. And the reverse: `0x061c6b3b` (+0% at $300 →
  +24% at $150), `0x39c9503f` (−0% → +16%), `0x42e9290e` (−32% → +13%),
  `0x4ad0eab9` (+9%/trimmed −9% → +19%/+13%).
- So **a single global threshold is the wrong knob**; bet size is a
  per-wallet signal. Two ways to use this, both worth doing:
  1. the B-tier books below (measure it forward, with exits and drag);
  2. a per-wallet `min_usd` chosen by the gate: evaluate each wallet at
     {300, 200, 150, 100}, pick the highest threshold that passes with the
     best trimmed ROI, store it on the Z record, and have the live path copy
     that wallet at ITS threshold (`LIVE_MIN_TRADER_BET_USD` becomes a
     default, the Z record an override).
- Caveat on absolute numbers: replay ROI ≠ ledger ROI. For today's gate
  passers, hold-to-resolution replay at $300 gives `0x9f15613e` +2% vs the
  B ledger's +27%, `0x3f3aa700` −6% vs +12%, `0xfd3e6449` −4% vs +15%: B's
  profit sits in mirrored exits (as memory says), which this replay does not
  model. Use the table for the *relative* effect of the threshold, and the
  forward books for the absolute answer.

### Forward test: B-tier books (required regardless of the backward result)

Run **B300 (current, untouched), B150 and B100** side by side as separate
paper books. Today `_copy_paper_b_loop` is one function reading
`CONFIG.copy_paper_b_*`; `CopyPaperRunner` itself is already parameterised
(`ledger_path`, `watchlist_path`, `extra_watchlist_paths`, `min_usd`, caps,
`blacklist_provider`, `strategy`). Needed:

1. Turn the B loop into a factory `run_b_book(book_id, min_usd)` with, per
   book: ledger `copy_paper_ledger_<id>.jsonl`, governance scope `<id>`
   (`promotion_state._scoped` then yields `promoted_wallets_<id>.json`,
   `copy_blacklist_<id>.json`, `promotion_offers_<id>.json`,
   `copy_retired_<id>.json`), gate history `promotion-gate-history_<id>.jsonl`,
   thread name and log tag `[COPY-PAPER-<ID>]`, own per-day caps env with
   the B300 values as defaults.
2. Config: `COPY_PAPER_B_BOOKS="b300:300,b150:150,b100:100"` (default
   `b300:300` = today's behaviour, same file names as today so nothing
   moves). `COPY_PAPER_B_LEDGER` stays the B300 ledger.
3. Consumers hard-wired to `CONFIG.copy_paper_b_ledger` keep reading B300:
   `zset_candidates.load_books`, `rehearsal.py:185`, `telegram_bot.py:652/1575/1921`,
   the race reporter (`main.py:1141/1154`), `ledger_integrity.py:176`,
   `scripts/seed_zset.py`, `scripts/strategy_compare.py`. Add
   `ZSET_GATE_BOOK` (default `b300`) so the owner can later point the Z gate
   at another book with one env change.
4. Shadow observer: shared, dedupes by `copy_id`, but its 40-quotes-per-sweep
   cap will be swamped by the $100 book's extra detections. Give each book a
   quote budget or raise the cap; quote B300 first.
5. **Decouple live from paper:** `live_budget.caps().min_trader_bet_usd`
   reads `COPY_PAPER_MIN_USD` (`live_budget.py:235`, enforced at
   `trade_executor.py:761`). Add `LIVE_MIN_TRADER_BET_USD` (default: the
   paper value) so lowering a paper book never lowers what real money copies.
6. Comparison: `scripts/strategy_compare.py` extended to N books; the 08:00
   digest carries one line per book (n, paper ROI, at-their-price ROI,
   real-quote ROI, exits share) after ≥100 settles each. Decide after 2-4
   weeks which book feeds the gate.

Cross-routing (`main.py:787-836`) only targets B300; leave it.

## 3.5 The two wallets the owner asked about (2026-09-24)

Neither is in Z (Z = 17 wallets). The "new copyable wallet" message adds a
wallet to the paper watchlist only.

- **0x9f6a4549…eb61** — weather-temperature bettor. Watchlist since 08-15;
  B offer 09-04 (n=15, +19%, Claude: "watch"); culled from A 09-21 (no
  winning category), cross-routed to B extras; re-admitted to the watchlist
  09-23. Gate today: 27 settled (needs 30), paper +8% (<10%), −4% with best 3
  deleted, A −17.5% over 11. Polymarket last 30 d: 1,183 buys all weather,
  median $6, 28 bets ≥$300, cash PnL −$26k, realized −$630. Latency on its
  trades 5-8 min. Not good.
- **0x18acd7b6…6ff9** — 5-minute "Bitcoin Up or Down" scalper. Found 09-22
  20:22 UTC. Last 30 d: 305 buys, 246 round-trips, median hold 1 min, 100%
  sold within 10 min, zero bets ≥$300, so B never copied it (0 rows).
  Discovery theory 1f ("early-exit swing … avg hold 0h") flagged exactly the
  uncopyable profile as a strength. Part 2 D2 (scalper rail) must also run
  inside discovery so such wallets never reach the watchlist or the phone.


---

# PART 4 — Priority and open decisions

Suggested order (each independently shippable):

1. **Part 2 A + C** (sell ≤ held shares; exchange reason + FAILED row). Real
   money is losing exits today. Half a day.
2. **Part 1 A-C** (equity excludes ALL resolved rows) + the env change for
   floor/daily. The floor is currently inert by ~$49. Half a day; the env
   change is minutes but needs the GitHub secret.
3. **Part 2 D1** (flip gate per trade) then **D2** (scalper rail in
   discovery + wallet_form). One day.
4. **Part 3 R1-R3** (gate thresholds, admit limit/cadence, probation
   pass/fail) with the A DECISION. One day.
5. **Part 3 forward books** (B150/B100 + live/paper min decoupling). Two days.
6. **Part 2 B** (proportional exits), **Part 1 E** (realized today from
   Polymarket claims), **Part 3 R4-R6**.

Open owner decisions:
- Part 3 §3.1: book A's role in the gate (recommended: real-quote slice as the
  rail, A as fallback; A keeps running).
- Part 3 §3.3 R3: probation pass/fail numbers (proposed ≥2 of 5 won and
  live at-their-price ROI ≥ −10%).
- Part 2 B / D: threshold defaults (trim <10% ignored, ≥90% full exit; flip
  gate at 50% sold; scalper rail at 20% of exits inside 10 min).
- Part 3 §3.4: which lower thresholds to run (proposed B150 and B100 next to
  B300).
