# ops digest 2026-09-24T20:19:56.715140+00:00 (last 24h)

## money state
{"cash": 75.745943, "open_cost": 32.0, "equity": 107.75, "floor": 30.0, "stated": 80.0, "spend": {"date": "2026-09-24", "spent_usd": 38.4, "cap_usd": 54.0, "remaining_usd": 15.6, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 67, "tier": {"1a": 0, "1b": 38.4, "1c": 0}, "ts": 1790280969.0897856, "day": "2026-09-24"}

## arm: {"armed": true, "ts": 1789919410.9079125, "by": "telegram", "reason": "", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-24", "spent_usd": 38.4, "wallet_copies": {"0x5213eb85fcd465c8927a8382f95dd2dc22306a35": 1, "0xd25156e222c9b907b128e27c36821fdb41db4d37": 1, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": 3, "0x722abb5460060870d46728bf45f66a6b1635d6ed": 1}, "wallet_copies_yesterday": {"0x722abb5460060870d46728bf45f66a6b1635d6ed": 1, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": 3, "0xd25156e222c9b907b128e27c36821fdb41db4d37": 1}, "yesterday": "2026-09-23", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x722abb5460060870d46728bf45f66a6b1635d6ed": {"wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed", "tier": "1b", "ts": 1789491938.939273, "source": "telegram-gate"}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"wallet": "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333", "tier": "1b", "ts": 1789752841.6491823, "source": "telegram-gate"}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"wallet": "0xf49614e63fb15383d4a9b717a1be03ad2410fe79", "tier": "1b", "ts": 1789827877.6900246, "source": "telegram-gate"}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"wallet": "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770", "tier": "1b", "ts": 1789992497.9469755, "source": "telegram-gate"}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"wallet": "0xd25156e222c9b907b128e27c36821fdb41db4d37", "tier": "1b", "ts": 1790166550.4519851, "source": "telegram-gate"}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43", "tier": "1b", "ts": 1790266340.2195778, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [38.4, 6], "1c": [0, 0]}
## probation: {"0x722abb5460060870d46728bf45f66a6b1635d6ed": {"since": 1789491935.7564917, "settled": 0}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"since": 1789752828.6614223, "settled": 0}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"since": 1789827868.9550335, "settled": 0}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"since": 1789992496.5955625, "settled": 0}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"since": 1790166548.6465027, "settled": 0}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"since": 1790266317.6788435, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
benched  0x00110b8e: 230 settled, 86% won vs 70% needed, net +16.8% on $204,966, worst day -2,112, 20 of 46 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x05878ac3: 126 settled, 47% won vs 49% needed, net +10.4% on $132,306, worst day -5,040, 4 of 56 exits under 10 min
benched  0x09b045ba: 34 settled, 74% won vs 59% needed, net +11.5% on $13,335, worst day -333, 33 of 33 exits under 10 min
benched  0x1985327e: 55 settled, 73% won vs 55% needed, net +17.3% on $21,122, worst day -535, 53 of 53 exits under 10 min
benched  0x3f3aa700: 225 settled, 50% won vs 55% needed, net -4.3% on $667,126, worst day -39,107, 0 of 5 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x4980930d: 3 settled, 0% won vs 34% needed, net -100.0% on $2,702, worst day -1,358
in form  0x5213eb85: 84 settled, 48% won vs 38% needed, net +6.4% on $41,372, worst day -2,314, 2 of 6 exits under 10 min
benched  0x57b25849: 37 settled, 51% won vs 48% needed, net -4.0% on $36,093, worst day -4,570
in form  0x722abb54: 87 settled, 79% won vs 76% needed, net +8.6% on $173,970, worst day -3,391, 8 of 72 exits under 10 min
benched  0x73653992: 7 settled, 86% won vs 74% needed, net +74.0% on $4,711, worst day -330, 0 of 5 exits under 10 min
in form  0x984ffef1: 31 settled, 68% won vs 52% needed, net +53.5% on $24,914, worst day -87, 2 of 6 exits under 10 min
benched  0x9f15613e: 348 settled, 53% won vs 48% needed, net +10.7% on $1,037,640, worst day -31,088, 12 of 19 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xd25156e2: 60 settled, 63% won vs 50% needed, net +20.3% on $35,452, worst day -1,488, 3 of 21 exits under 10 min (capped: 9.7 of 14 days read, 5500 rows)
benched  0xd970693a: 36 settled, 69% won vs 58% needed, net +6.9% on $13,518, worst day -324, 36 of 36 exits under 10 min
benched  0xeef6ad0e: no settled bets on our slice in 14 days
benched  0xf49614e6: 72 settled, 51% won vs 50% needed, net +11.4% on $248,179, worst day -11,771, 4 of 10 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xf9168343: 55 settled, 55% won vs 47% needed, net +4.0% on $150,786, worst day -6,320, 2 of 34 exits under 10 min
benched  0xfd3e6449: 69 settled, 67% won vs 72% needed, net +1.5% on $48,839, worst day -2,632, 18 of 21 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
two clocks: 1302 matched fills over 1.0 d, api lag p50 18.0s, chain lag p50 2.4s, chain earlier by 15.3s at the median; api-only 139, chain-only 415, replayed rows 0; CHAIN IS PRIMARY
⏱ api lag cost, last 7d (estimate): +9.42 USD over 2454 fills at $6.40 each, +0.000 USD a fill at the median, chain earlier by 13.8s

## watcher (16 wakes in 24h)
{"ts": 1790210951.937275, "kind": "nothing", "woke_because": "7984db4fdbb9", "concluded": "The cause is the known unclaimed winnings problem tying up cash so the CLOB rejects new orders, and the woke line is only the bot's own escalation_delivered INFO confirming it already sent this to the owner's phone. The message itself says the owner was already told, and this is the routine escalation path w
{"ts": 1790254189.689103, "kind": "analyst", "woke_because": "daily study", "concluded": "67 dollars of resolved winnings sit unredeemed yet are counted as spendable while liquid USDC is only 22.86. This is the same fault (534614711c15) that got two live orders rejected today with 400s; redeem the winnings, or stop counting resolved_unclaimed toward available cash, so the bot stops approving order
{"ts": 1790254189.689103, "kind": "analyst", "woke_because": "daily study", "concluded": "21.59 USD across 37 would have won copies were declined only because LIVE_MAX_PER_WALLET_DAY of 3 was already hit (293 of 588 declines were at that cap), making it the single largest source of turned away winners. Raising exposure is yours alone, so flagging it in case the 3 per wallet ceiling is now tighter 
{"ts": 1790254189.689103, "kind": "analyst", "woke_because": "daily study", "concluded": "Unredeemed 67 dollar winnings inflate spendable cash and cost 2 rejected orders today; the 3 per wallet cap turned away 37 winners worth +21.59.", "did": "2 proposal(s): noted; noted", "cost_usd": 0.3619175}
{"ts": 1790263063.103282, "kind": "analyst", "woke_because": "daily study", "concluded": "Over book B's own rows, how many copies collapse to one per market if we keep only each wallet's first entry, and does replayed ROI hold versus copying every buy?", "did": "study 2026-09-24-first_entry-152981e2 frozen: wallets in 18 -> 18 (stay 18, enter 0, leave 0); copies 3276 -> 3276; ROI at their price +3
{"ts": 1790263063.103282, "kind": "analyst", "woke_because": "daily study", "concluded": "67 dollars of resolved winnings are still counted as spendable while liquid USDC is only 22.86, and that overstatement caused 2 live order rejections today (fingerprint 534614711c15); redeeming the winnings clears the fault at its source.", "did": "noted", "cost_usd": 0.0}
{"ts": 1790263063.103282, "kind": "analyst", "woke_because": "study 2026-09-24-first_entry-152981e2", "concluded": "0 of 3276 copies collapsed and replayed ROI held flat at +3.5%, because both arms ran first_entry_only=true so nothing was actually varied. This tells the bot nothing about first-entry-only versus copying every buy, since the study compared the current setting to itself.", "did": "co
{"ts": 1790263063.103282, "kind": "analyst", "woke_because": "daily study", "concluded": "Study first-entry-only: it could free the 3/day wallet cap that turned away 37 winners worth +42.75. Also redeem the 67 dollars of unclaimed winnings that caused 2 order rejections.", "did": "3 proposal(s): study 2026-09-24-first_entry-152981e2 frozen: wallets in 18 ; noted; concluded; one question the menu c
{"ts": 1790263806.907095, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 72, start 1 today)", "did": "started min150 (pid 72, start 1 today)", "cost_usd": 0.0}
{"ts": 1790264844.3604205, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 7, start 2 today)", "did": "started min150 (pid 7, start 2 today)", "cost_usd": 0.0}
{"ts": 1790265495.531029, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 6, first start since this supervisor came up)", "did": "started min150 (pid 6, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790265615.5461192, "kind": "note", "woke_because": "ab787115fd71, 9d498e122ffb, 680493f22dc3", "concluded": "Cause: the deployed build (sha e18a503) added a fast-exit statistic and a bench rule keyed on exits under 10 minutes, which produced these new form-report shapes (ab787115fd71, 9d498e122ffb, 680493f22dc3, the last differing only by comma formatting of a million-dollar figure). These
{"ts": 1790266294.9381447, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 6, first start since this supervisor came up)", "did": "started min150 (pid 6, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790266414.9428663, "kind": "note", "woke_because": "b04bf1a60c1d, 89a855d4a192, cf4709ce7c00, 852039760707, 9713155b03b8", "concluded": "A probation-window expiry batch ran at the 16:11:35 restart and evicted every wallet whose 10-day probation produced too few settled copies, and the gate counts zero settled copies (0 of 0 won) as a failure, so wallets that simply stayed quiet were droppe
{"ts": 1790267813.06647, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 6, first start since this supervisor came up)", "did": "started min150 (pid 6, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790269134.9521146, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150 (pid 6, first start since this supervisor came up)", "did": "started min150 (pid 6, first start since this supervisor came up)", "cost_usd": 0.0}
## live limits (owner's number, and the analyst's where one is in force)
LIVE_MAX_PER_WALLET_DAY: 3 (owner) band 1..3
FETCH_INTERVAL: 3.0 (owner) band 2..5
OPS_REARM_CLEAR_S: 900.0 (owner) band 600.0..1800.0
OPS_REARM_MAX_PER_DAY: 3 (owner) band 1..3
FORM_DAYS: 14.0 (owner) band 7.0..21.0
## book B at each slice floor (raw numbers; the gate reads the one marked)
b300 (floor $300): 7280 settled, 254 open, realized +1.8%, at their price +2.8% (net -8.0%), win rate 57%, feeds the Z gate
b150 (floor $150): 66 settled, 55 open, realized -10.9%, at their price -9.9% (net -20.7%), win rate 48%
b100 (floor $100): 85 settled, 59 open, realized -5.5%, at their price -4.5% (net -15.2%), win rate 48%
## near the Z door (32 wallets within 2 fails; 5 pass and wait)
0x00110b8e: 1 fail(s): not a scalper at our latency (scalper: 43% of exits within 10 min; uncopyable at our latency)
0x09b045ba: 1 fail(s): not a scalper at our latency (scalper: 100% of exits within 10 min; uncopyable at our latency)
0x10658d37: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (23 clean (of 23 all-time))
0x19585131: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (19 clean (of 19 all-time))
0x1985327e: 1 fail(s): not a scalper at our latency (scalper: 100% of exits within 10 min; uncopyable at our latency)
0x3968f7c9: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (17 clean (of 17 all-time))
0x4a3f86ed: 1 fail(s): promotion floor still holds (copy ROI +4% < floor +10%)
0x57b25849: 1 fail(s): promotion floor still holds (copy ROI +7% < floor +10%; 2nd-half ROI -10% < -10% (edge decaying))
0x8342720d: 1 fail(s): still positive with its best 3 copies deleted (-0% over 45 copies with its best 3 deleted)
0x91c7d990: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (17 clean (of 17 all-time))
0x9f15613e: 1 fail(s): not a scalper at our latency (scalper: 63% of exits within 10 min; uncopyable at our latency)
0xa42f3648: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (19 clean (of 19 all-time))
## experiments (the analyst's cards; one live at a time)
min150           live   slice floor 300 to 150                             no check  (min150 <- study 2026-09-24-min_usd-cdc749c5)
{"day": "2026-09-24", "id": "min150", "event": "queued"}
{"day": "2026-09-24", "id": "min150", "event": "live"}
study 2026-09-24-first_entry-152981e2: wallets in 18 -> 18 (stay 18, enter 0, leave 0); copies 3276 -> 3276; ROI at their price +3.5% -> +3.5%
study 2026-09-24-min_usd-cdc749c5: wallets in 19 -> 20 (stay 15, enter 5, leave 4); copies 3567 -> 5216; ROI at their price +2.6% -> +3.7%
## questions the study menu could not compute (last 7 days)
2026-09-24 after study 2026-09-24-first_entry-152981e2: With first_entry_only=false as the baseline (copying every buy), how many copies collapse to one per market when we switch it on, and does the +3.5% ROI hold? (missing: This run set both the from and to arms to first_entry_only=true, so there is no every-buy baseline in the frozen table to difference against.)
## fingerprints (30 shown)
54ac26fb3ff1 x48 last 0.0h ago [open: 48 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/price body={'S':'S'}
69fd3dc7d27e x17 last 1.5h ago [open: 17 hits, no action yet] :: INFO [daily-cap] +$N (copy:Nb) reserved | total today $N / $N
eb7da12386c6 x17 last 1.5h ago [open: 17 hits, no action yet] :: TRADE [LIVE] BUY $N on 'S' @ N, order <hex>...
a77088f7944a x17 last 1.5h ago [open: 17 hits, no action yet] :: INFO [tiered-risk] Recorded tier Nb placement: $N | open: $N / $N
d7140f640d29 x16 last 1.5h ago [open: 16 hits, no action yet] :: TRADE [verify] FILLED: BUY N shares on 'S' @ N
6c813168939b x4 last 1.5h ago [open: 4 hits, no action yet] :: ERROR [py_clob_client_v2] request error: Server disconnected
6f12d4998994 x18 last 3.3h ago [open: 18 hits, no action yet] :: INFO [recovery] No pending orders to recover
6b829965c182 x18 last 3.3h ago [open: 18 hits, no action yet] :: INFO Bot started. Monitoring trades...
c47d62e70341 x18 last 3.4h ago [open: 18 hits, no action yet] :: INFO Received signal N, shutting down...
9d8a6d2794ec x11 last 3.4h ago [open: 11 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/auth/api-key body={'S':'S'}
c3db66a087f7 x3 last 4.1h ago [open: 3 hits, no action yet] :: WARNING [zset] ADMITTED <hex> to set Z (N over N copies with its best N deleted). Real money may now follow it once arme
790247505aab x3 last 4.1h ago [open: 3 hits, no action yet] :: INFO [ops] auto_admit: 'S' -> 'S' | N settled paper copies, paper ROI N, trimmed N, ideal N
9d498e122ffb x4 last 4.1h ago [open: 4 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N, N of N exits under N min
b04bf1a60c1d x9 last 4.1h ago [open: 9 hits, no action yet] :: WARNING [zset] EVICTED <hex> from set Z: probation failed: N of N won, realized N on $N (pass needs N won and N)
89a855d4a192 x9 last 4.1h ago [open: 9 hits, no action yet] :: INFO [ops] evict: 'S' -> 'S' | probation failed: N of N won, realized N on $N (pass needs N won and N)
cf4709ce7c00 x1 last 4.1h ago [open: 1 hits, no action yet] :: INFO [ops] probation_failed: 'S' -> 'S' | lost N on 'S'LoL: Team WE vs JD Gami | Evict is reversible: /zset readmit
852039760707 x7 last 4.1h ago [open: 7 hits, no action yet] :: INFO [ops] probation_failed: 'S' -> 'S' | | Evict is reversible: /zset readmit
9713155b03b8 x1 last 4.1h ago [open: 1 hits, no action yet] :: INFO [ops] probation_failed: 'S' -> 'S' | lost N on 'S'Dota N: Pipsqueak+N vs | Evict is reversible: /zset readmit
ab787115fd71 x1 last 4.3h ago [open: 1 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N, N of N exits under N min (c
680493f22dc3 x1 last 4.3h ago [open: 1 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N,N, worst day N, N of N exits under N min 
fe47bbb56041 x7 last 9.4h ago [open: 7 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N
34253fa6334e x4 last 12.3h ago [open: 4 hits, no action yet] :: INFO [AB-RACE] rehearsal line sent, real-money line sent
c6d91d798e54 x11 last 14.6h ago [open: 11 hits, no action yet] :: INFO [tiered-risk] tier Nb: released $N of exposure from resolved or closed positions | open now: $N
d96f6949e1c9 x3 last 15.4h ago [open: 3 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N,N, worst day N (capped: window read in fu
7984db4fdbb9 x1 last 19.5h ago [open: 1 hits, no action yet] :: INFO [ops] escalation_delivered: 'S' -> 'S' | Second order rejection today from the unclaimed winnings problem you were 
534614711c15 x2 last 21.0h ago [open: 2 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/order body={'S':'S'}
eb6ff024b864 x1 last 29.5h ago [open: 1 hits, no action yet] :: INFO [verify] UNFILLED, cancelled order <hex>...
c01c65915062 x1 last 31.8h ago [open: 1 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N (capped: N of N days read, N
2497cd50ff7d x2 last 50.8h ago [open: 2 hits, no action yet] :: INFO [ops] settled: 'S' -> 'S' | lost N on 'S' (<hex>, tier Nb)
9252b71ae332 x2 last 50.8h ago [open: 2 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N (capped: window read in full

## ledger (43 rows)
{"ts": 1790203785.9754703, "day": "2026-09-23", "kind": "form", "before": "0x5213eb85 benched", "after": "in form", "detail": "0x5213eb85: 81 settled, 46% won vs 37% needed, net +2.4% on $40,140, worst day -2,314", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1790203785.9754703, "day": "2026-09-23", "kind": "form", "before": "0x9f15613e in form", "after": "benched", "detail": "0x9f15613e: 356 settled, 51% won vs 48% needed, net +8.4% on $1,065,336, worst day -31,088 (capped: window read in full, older lookback cut, 5500 rows)", "push": "WALLET", "wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3"}
{"ts": 1790210841.5089324, "day": "2026-09-24", "kind": "escalation_delivered", "before": "routine escalation", "after": "sent", "detail": "Second order rejection today from the unclaimed winnings problem you were already told about. 07:49:59 UTC rejected a bu", "push": "BOT"}
{"ts": 1790225604.6871822, "day": "2026-09-24", "kind": "form", "before": "0x5213eb85 in form", "after": "benched", "detail": "0x5213eb85: 84 settled, 44% won vs 38% needed, net -1.4% on $41,656, worst day -2,314", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1790225604.6871822, "day": "2026-09-24", "kind": "form", "before": "0x57b25849 in form", "after": "benched", "detail": "0x57b25849: 38 settled, 50% won vs 48% needed, net -5.3% on $36,620, worst day -4,570", "push": "WALLET", "wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2"}
{"ts": 1790225604.6871822, "day": "2026-09-24", "kind": "form", "before": "0x9f15613e benched", "after": "in form", "detail": "0x9f15613e: 345 settled, 52% won vs 48% needed, net +10.0% on $1,031,210, worst day -31,088 (capped: window read in full, older lookback cut, 5500 rows)", "push": "WALLET", "wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3"}
{"ts": 1790247359.7616093, "day": "2026-09-24", "kind": "form", "before": "0x5213eb85 benched", "after": "in form", "detail": "0x5213eb85: 80 settled, 46% won vs 37% needed, net +2.3% on $39,160, worst day -2,314", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1790254189.6389196, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790255604.3749578, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790260564.5466104, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790262133.8947597, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790262966.2169752, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790263063.103282, "day": "2026-09-24", "kind": "analyst_study", "before": "2026-09-24-first_entry-152981e2", "after": "wallets in 18 -> 18 (stay 18, enter 0, leave 0); copies 3276 -> 3276; ROI at their price +3.5% -> +3.5%", "detail": "estimate: 40 of 182 wallets studied (most settled first); activity rows capped at 5,500 per wallet by the data api (22 capped, marked *); in = the form rail's v", "push": "BOT"}
{"ts": 1790264844.0728428, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790265495.0026383, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790265510.7714798, "day": "2026-09-24", "kind": "form", "before": "0x00110b8e in form", "after": "benched", "detail": "0x00110b8e: 230 settled, 86% won vs 70% needed, net +16.8% on $204,966, worst day -2,112, 20 of 46 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)", "push": "WALLET", "wallet": "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333"}
{"ts": 1790265510.7714798, "day": "2026-09-24", "kind": "form", "before": "0x09b045ba in form", "after": "benched", "detail": "0x09b045ba: 34 settled, 74% won vs 59% needed, net +11.5% on $13,335, worst day -333, 33 of 33 exits under 10 min", "push": "WALLET", "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6"}
{"ts": 1790265510.7714798, "day": "2026-09-24", "kind": "form", "before": "0x1985327e in form", "after": "benched", "detail": "0x1985327e: 55 settled, 73% won vs 55% needed, net +17.3% on $21,122, worst day -535, 53 of 53 exits under 10 min", "push": "WALLET", "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab"}
{"ts": 1790265510.7714798, "day": "2026-09-24", "kind": "form", "before": "0x9f15613e in form", "after": "benched", "detail": "0x9f15613e: 348 settled, 53% won vs 48% needed, net +10.7% on $1,037,640, worst day -31,088, 12 of 19 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)", "push": "WALLET", "wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3"}
{"ts": 1790265510.7714798, "day": "2026-09-24", "kind": "form", "before": "0xd970693a in form", "after": "benched", "detail": "0xd970693a: 36 settled, 69% won vs 58% needed, net +6.9% on $13,518, worst day -324, 36 of 36 exits under 10 min", "push": "WALLET", "wallet": "0xd970693a3384dc762b191707a4927ac3814bbbba"}
{"ts": 1790266294.4568505, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790266312.4230769, "day": "2026-09-24", "kind": "evict", "before": "0x05878ac3 in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 2 won, realized -99.9% on $12.80 (pass needs 2 won and -10%)", "push": null, "wallet": "0x05878ac343c1387d592042d788424412733ac40b"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x05878ac3 on probation (10 days on probation)", "after": "evicted: 0 of 2 won, realized -99.9% on $12.80 (pass needs 2 won and -10%)", "detail": "lost -6.39 on 'LoL: T1 Academy vs KT R; lost -6.40 on 'LoL: Team WE vs JD Gami | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x05878ac343c1387d592042d788424412733ac40b", "trial": [{"token_id": "45664770486754830410276385709296820028038533040592413432582939697519809216911", "pnl": -6.39, "won": false}, {"token_id": "86842978223026466862449934105595250822075305679428664631958332197768084254089", "pnl": -6.4, "won": false}]}
{"ts": 1790266312.4604638, "day": "2026-09-24", "kind": "evict", "before": "0x09b045ba in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x09b045ba on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "trial": []}
{"ts": 1790266312.707255, "day": "2026-09-24", "kind": "evict", "before": "0x1985327e in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x1985327e on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "trial": []}
{"ts": 1790266312.9666994, "day": "2026-09-24", "kind": "evict", "before": "0x4980930d in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x4980930d on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "trial": []}
{"ts": 1790266313.7157757, "day": "2026-09-24", "kind": "evict", "before": "0x5213eb85 in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x5213eb85 on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "trial": []}
{"ts": 1790266315.196664, "day": "2026-09-24", "kind": "evict", "before": "0x57b25849 in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 2 won, realized -100.0% on $12.80 (pass needs 2 won and -10%)", "push": null, "wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x57b25849 on probation (10 days on probation)", "after": "evicted: 0 of 2 won, realized -100.0% on $12.80 (pass needs 2 won and -10%)", "detail": "lost -6.40 on 'Counter-Strike: Bounty ; lost -6.40 on 'Dota 2:  Pipsqueak+4 vs | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2", "trial": [{"token_id": "96998131034687394987869300990474810645455355843214977734260368889207437752543", "pnl": -6.4, "won": false}, {"token_id": "7176164693333913912271980594552279937832227503542042198140094468727106225171", "pnl": -6.4, "won": false}]}
{"ts": 1790266315.7095141, "day": "2026-09-24", "kind": "evict", "before": "0x73653992 in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0x73653992 on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da", "trial": []}
{"ts": 1790266316.1909883, "day": "2026-09-24", "kind": "evict", "before": "0xd970693a in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0xd970693a3384dc762b191707a4927ac3814bbbba"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0xd970693a on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0xd970693a3384dc762b191707a4927ac3814bbbba", "trial": []}
{"ts": 1790266316.9353566, "day": "2026-09-24", "kind": "evict", "before": "0xeef6ad0e in set Z", "after": "evicted (sticky)", "detail": "probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "push": null, "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "probation_failed", "before": "0xeef6ad0e on probation (10 days on probation)", "after": "evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)", "detail": " | Evict is reversible: /zset readmit", "push": "WALLET", "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c", "trial": []}
{"ts": 1790266317.6788435, "day": "2026-09-24", "kind": "auto_admit", "before": "0x984ffef1 not in Z", "after": "in set Z, on probation", "detail": "30 settled paper copies, paper ROI +34.0%, trimmed +20.2%, ideal +35.0%", "push": "WALLET", "wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43"}
{"ts": 1790266290.46136, "day": "2026-09-24", "kind": "form", "before": "0x984ffef1 unknown", "after": "in form", "detail": "0x984ffef1: 31 settled, 68% won vs 52% needed, net +53.5% on $24,914, worst day -87, 2 of 6 exits under 10 min", "push": null, "wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43"}
{"ts": 1790267812.5348933, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790269134.4726067, "day": "2026-09-24", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}

## important lines (333)
2026-09-23 20:26:05 ERROR Error fetching NEG_RISK_CTF events [94326691-94326691]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 20:26:39 ERROR Error fetching CTF events [94326713-94326714]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 20:36:06 ERROR Error fetching CTF events [94327091-94327092]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 20:36:06 ERROR Error fetching NEG_RISK_CTF events [94327091-94327092]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 20:39:58 ERROR Error fetching NEG_RISK_CTF events [94327246-94327247]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:10:05 ERROR Error fetching NEG_RISK_CTF events [94328448-94328451]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:10:10 ERROR Error fetching NEG_RISK_CTF events [94328452-94328455]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:10:15 ERROR Error fetching CTF events [94328456-94328458]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:10:23 ERROR Error fetching NEG_RISK_CTF events [94328459-94328463]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:16:35 ERROR Error fetching NEG_RISK_CTF events [94328707-94328711]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:16:42 ERROR Error fetching NEG_RISK_CTF events [94328712-94328715]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:28:42 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-23 21:49:20 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-23 21:54:09 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $32.00 / $32.00
2026-09-23 21:54:10 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $19.20 / $200.00
2026-09-23 21:59:46 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-23 22:05:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-23 22:47:19 ERROR Error fetching CTF events [94332320-94332321]: {'code': -32002, 'message': 'request timed out'}
2026-09-23 22:50:42 INFO  [ops] form: '0x5213eb85 benched' -> 'in form' | 0x5213eb85: 81 settled, 46% won vs 37% needed, net +2.4% on $40,140, worst day -2,314
2026-09-23 22:51:02 INFO  [ops] form: '0x9f15613e in form' -> 'benched' | 0x9f15613e: 356 settled, 51% won vs 48% needed, net +8.4% on $1,065,336, worst day -31,088 (capped: window read in full, older lookback cut, 5500 rows)
2026-09-23 23:01:04 ERROR Error fetching CTF events [94332889-94332891]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 23:01:04 ERROR Error fetching NEG_RISK_CTF events [94332889-94332891]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 23:18:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/order body={"error":"not enough balance / allowance: the balance is not enough -\u003e balance: 20000000, order amount: 20830000"}
2026-09-23 23:18:14 ERROR [exec] Order placement failed: PolyApiException[status_code=400, error_message={'error': 'not enough balance / allowance: the balance is not enough -> balance: 20000000, order amount: 20830000'}]
2026-09-23 23:18:14 ERROR [exec] Order placement returned None for 'Buenos Aires 2: Francisco Comesana vs Jo'
2026-09-23 23:21:20 ERROR Error fetching CTF events [94333701-94333702]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 23:21:21 ERROR Error fetching NEG_RISK_CTF events [94333701-94333702]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 00:19:58 ERROR Error fetching NEG_RISK_CTF events [94336026-94336027]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 00:22:17 ERROR Error fetching CTF events [94336138-94336139]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 00:25:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 00:25:38 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 00:26:18 ERROR Error fetching NEG_RISK_CTF events [94336280-94336280]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 00:29:18 ERROR Error fetching CTF events [94336399-94336400]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 00:36:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 00:36:15 ERROR Error fetching NEG_RISK_CTF events [94336678-94336678]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 00:47:22 INFO  [ops] escalation_delivered: 'routine escalation' -> 'sent' | Second order rejection today from the unclaimed winnings problem you were already told about. 07:49:59 UTC rejected a bu
2026-09-24 01:12:34 ERROR Error fetching NEG_RISK_CTF events [94338150-94338151]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:19:12 ERROR Error fetching CTF events [94338415-94338416]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:27:37 ERROR Error fetching CTF events [94338752-94338753]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:27:37 ERROR Error fetching NEG_RISK_CTF events [94338752-94338753]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:36:03 ERROR Error fetching CTF events [94339089-94339090]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:36:03 ERROR Error fetching NEG_RISK_CTF events [94339089-94339090]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:47:04 ERROR Error fetching CTF events [94339530-94339531]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:47:07 ERROR Error fetching NEG_RISK_CTF events [94339532-94339532]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:48:39 ERROR Error fetching CTF events [94339593-94339594]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:53:07 ERROR Error fetching NEG_RISK_CTF events [94339772-94339773]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:58:40 ERROR Error fetching CTF events [94339994-94339995]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 01:58:40 ERROR Error fetching NEG_RISK_CTF events [94339994-94339995]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:07:12 ERROR Error fetching NEG_RISK_CTF events [94340335-94340336]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:09:27 ERROR Error fetching CTF events [94340426-94340426]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:09:52 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 02:36:55 ERROR Error fetching NEG_RISK_CTF events [94341522-94341522]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:36:57 ERROR Error fetching NEG_RISK_CTF events [94341523-94341524]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:46:07 ERROR Error fetching CTF events [94341890-94341891]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:48:36 ERROR Error fetching NEG_RISK_CTF events [94341989-94341990]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:48:38 ERROR Error fetching NEG_RISK_CTF events [94341991-94341991]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:55:25 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $6.40 / $32.00
2026-09-24 02:55:27 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $25.60 / $200.00
2026-09-24 02:58:45 ERROR Error fetching CTF events [94342395-94342396]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 02:58:45 ERROR Error fetching NEG_RISK_CTF events [94342395-94342396]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:04:42 ERROR Error fetching CTF events [94342613-94342614]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 03:16:20 ERROR Error fetching CTF events [94343097-94343098]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:16:20 ERROR Error fetching NEG_RISK_CTF events [94343097-94343098]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:16:39 ERROR Error fetching CTF events [94343110-94343110]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:16:39 ERROR Error fetching NEG_RISK_CTF events [94343110-94343110]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:33:04 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $19.20
2026-09-24 03:36:05 ERROR Error fetching CTF events [94343885-94343886]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 03:45:17 ERROR Error fetching NEG_RISK_CTF events [94344253-94344255]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:00:45 ERROR Error fetching CTF events [94344853-94344853]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 04:16:07 ERROR Error fetching NEG_RISK_CTF events [94345487-94345488]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:19:54 ERROR Error fetching CTF events [94345639-94345640]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:23:32 ERROR Error fetching CTF events [94345784-94345785]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:23:32 ERROR Error fetching NEG_RISK_CTF events [94345784-94345785]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:28:18 ERROR Error fetching NEG_RISK_CTF events [94345950-94345956]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 04:31:06 ERROR Error fetching CTF events [94346086-94346087]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:31:06 ERROR Error fetching NEG_RISK_CTF events [94346086-94346087]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:54:03 INFO  [ops] form: '0x5213eb85 in form' -> 'benched' | 0x5213eb85: 84 settled, 44% won vs 38% needed, net -1.4% on $41,656, worst day -2,314
2026-09-24 04:54:09 INFO  [ops] form: '0x57b25849 in form' -> 'benched' | 0x57b25849: 38 settled, 50% won vs 48% needed, net -5.3% on $36,620, worst day -4,570
2026-09-24 04:54:22 INFO  [ops] form: '0x9f15613e benched' -> 'in form' | 0x9f15613e: 345 settled, 52% won vs 48% needed, net +10.0% on $1,031,210, worst day -31,088 (capped: window read in full, older lookback cut, 5500 rows)
2026-09-24 04:55:56 ERROR Error fetching NEG_RISK_CTF events [94347060-94347061]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 04:56:11 ERROR Error fetching CTF events [94347090-94347091]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 04:56:11 ERROR Error fetching NEG_RISK_CTF events [94347090-94347091]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 05:26:01 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $12.80
2026-09-24 05:40:04 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-24 05:40:04 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-24 05:40:04 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-24 05:41:48 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $6.40
2026-09-24 06:02:54 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-24 06:06:01 ERROR Error fetching CTF events [94349881-94349884]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:06:01 ERROR Error fetching NEG_RISK_CTF events [94349881-94349884]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:06:04 ERROR Error fetching CTF events [94349885-94349886]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:21:06 ERROR Error fetching NEG_RISK_CTF events [94350486-94350487]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:21:46 ERROR Error fetching CTF events [94350513-94350514]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:31:06 ERROR Error fetching CTF events [94350886-94350888]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:31:06 ERROR Error fetching NEG_RISK_CTF events [94350886-94350888]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 06:46:05 ERROR Error fetching NEG_RISK_CTF events [94351486-94351487]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:00:10 INFO  [AB-RACE] rehearsal line sent, real-money line sent
2026-09-24 08:01:42 ERROR Error fetching CTF events [94354510-94354511]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:01:42 ERROR Error fetching NEG_RISK_CTF events [94354510-94354511]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:07:56 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $12.80 / $32.00
2026-09-24 08:07:57 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $12.80 / $200.00
2026-09-24 08:21:39 ERROR Error fetching CTF events [94355308-94355309]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:28:22 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 08:29:06 ERROR Error fetching NEG_RISK_CTF events [94355587-94355587]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 08:34:49 ERROR Error fetching NEG_RISK_CTF events [94355835-94355836]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:35:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 08:40:22 ERROR Error fetching CTF events [94356057-94356058]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:40:22 ERROR Error fetching NEG_RISK_CTF events [94356057-94356058]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:42:54 ERROR Error fetching CTF events [94356158-94356159]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:46:05 ERROR Error fetching CTF events [94356286-94356287]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 08:46:05 ERROR Error fetching NEG_RISK_CTF events [94356286-94356287]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:17:02 ERROR Error fetching CTF events [94357524-94357525]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:28:00 ERROR Error fetching CTF events [94357963-94357963]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:28:00 ERROR Error fetching NEG_RISK_CTF events [94357963-94357963]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:28:02 ERROR Error fetching NEG_RISK_CTF events [94357964-94357965]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:41:05 ERROR Error fetching CTF events [94358486-94358487]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:41:06 ERROR Error fetching NEG_RISK_CTF events [94358486-94358487]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:51:21 ERROR Error fetching CTF events [94358897-94358898]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:54:28 ERROR Error fetching CTF events [94359021-94359022]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:54:28 ERROR Error fetching NEG_RISK_CTF events [94359021-94359022]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 09:55:13 ERROR Error fetching CTF events [94359052-94359052]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:28:57 ERROR Error fetching CTF events [94360399-94360400]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:28:57 ERROR Error fetching NEG_RISK_CTF events [94360399-94360400]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:32:20 ERROR Error fetching CTF events [94360535-94360535]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:38:20 ERROR Error fetching CTF events [94360755-94360755]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 10:39:59 ERROR Error fetching NEG_RISK_CTF events [94360821-94360821]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 10:42:49 ERROR Error fetching CTF events [94360954-94360955]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:44:04 ERROR Error fetching CTF events [94361004-94361005]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:48:26 ERROR Error fetching NEG_RISK_CTF events [94361179-94361180]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:50:41 ERROR Error fetching CTF events [94361269-94361270]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 10:50:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 10:56:49 INFO  [ops] form: '0x5213eb85 benched' -> 'in form' | 0x5213eb85: 80 settled, 46% won vs 37% needed, net +2.3% on $39,160, worst day -2,314
2026-09-24 11:00:50 ERROR Error fetching NEG_RISK_CTF events [94361655-94361656]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 11:32:02 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $19.20 / $32.00
2026-09-24 11:32:03 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $19.20 / $200.00
2026-09-24 11:36:06 ERROR Error fetching CTF events [94363085-94363086]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 11:36:06 ERROR Error fetching NEG_RISK_CTF events [94363085-94363086]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 11:56:06 ERROR Error fetching CTF events [94363886-94363887]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:14:27 ERROR Error fetching CTF events [94364620-94364621]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:15:03 ERROR Error fetching CTF events [94364644-94364645]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:15:32 ERROR Error fetching CTF events [94364663-94364664]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:15:32 ERROR Error fetching NEG_RISK_CTF events [94364663-94364664]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:26:02 ERROR Error fetching CTF events [94365064-94365064]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 12:28:47 ERROR Error fetching CTF events [94365194-94365194]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:28:50 ERROR Error fetching NEG_RISK_CTF events [94365195-94365196]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:31:08 ERROR Error fetching CTF events [94365287-94365288]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:33:07 ERROR Error fetching CTF events [94365366-94365367]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:33:07 ERROR Error fetching NEG_RISK_CTF events [94365366-94365367]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:36:28 ERROR Error fetching CTF events [94365499-94365500]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:42:14 ERROR Error fetching CTF events [94365709-94365710]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 12:47:05 ERROR Error fetching CTF events [94365903-94365903]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 12:49:20 INFO  Received signal 15, shutting down...
2026-09-24 12:49:43 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 12:49:44 INFO  Bot started. Monitoring trades...
2026-09-24 12:53:19 ERROR Error fetching CTF events [94366170-94366173]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 12:53:19 ERROR Error fetching NEG_RISK_CTF events [94366170-94366173]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 13:03:56 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $25.60 / $32.00
2026-09-24 13:03:57 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $25.60 / $200.00
2026-09-24 13:06:09 ERROR [inventory] API sync failed: 
2026-09-24 13:11:45 ERROR Error fetching NEG_RISK_CTF events [94366872-94366888]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 13:12:53 INFO  Received signal 15, shutting down...
2026-09-24 13:13:22 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 13:13:23 INFO  Bot started. Monitoring trades...
2026-09-24 13:15:06 ERROR Error fetching CTF events [94367024-94367024]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 13:18:29 ERROR Error fetching CTF events [94367176-94367178]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 13:29:42 ERROR Error fetching NEG_RISK_CTF events [94367602-94367607]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 13:34:03 ERROR Error fetching NEG_RISK_CTF events [94367777-94367781]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 13:35:21 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-24 13:39:55 ERROR Error fetching CTF events [94368033-94368036]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 13:46:54 ERROR Error fetching NEG_RISK_CTF events [94368292-94368294]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 14:22:23 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 14:22:24 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 14:24:06 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $32.00 / $32.00
2026-09-24 14:24:07 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $32.00 / $200.00
2026-09-24 14:26:25 ERROR Error fetching CTF events [94369896-94369896]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 14:26:25 ERROR Error fetching NEG_RISK_CTF events [94369896-94369896]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 14:33:02 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 14:35:26 INFO  Received signal 15, shutting down...
2026-09-24 14:36:18 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 14:36:18 INFO  Bot started. Monitoring trades...
2026-09-24 14:38:27 ERROR Error fetching CTF events [94370357-94370357]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 14:39:14 ERROR Error fetching CTF events [94370382-94370388]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:01:42 INFO  Received signal 15, shutting down...
2026-09-24 15:02:06 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 15:02:07 INFO  Bot started. Monitoring trades...
2026-09-24 15:10:46 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-24 15:10:46 ERROR Network error fetching 0x0587...c40b: 
2026-09-24 15:10:46 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-24 15:10:46 ERROR Network error fetching 0x09b0...a3b6: 
2026-09-24 15:10:46 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-24 15:14:03 ERROR Error fetching NEG_RISK_CTF events [94371769-94371781]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:15:30 INFO  Received signal 15, shutting down...
2026-09-24 15:16:13 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 15:16:13 INFO  Bot started. Monitoring trades...
2026-09-24 15:28:21 ERROR Error fetching CTF events [94372350-94372353]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:29:06 ERROR Error fetching CTF events [94372382-94372383]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:41:26 ERROR Error fetching CTF events [94372875-94372876]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:46:52 INFO  Received signal 15, shutting down...
2026-09-24 15:47:17 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 15:47:18 INFO  Bot started. Monitoring trades...
2026-09-24 15:48:38 ERROR Error fetching CTF events [94373164-94373165]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:57:43 INFO  Received signal 15, shutting down...
2026-09-24 15:58:12 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 15:58:13 INFO  Bot started. Monitoring trades...
2026-09-24 15:58:45 INFO  [ops] form: '0x00110b8e in form' -> 'benched' | 0x00110b8e: 230 settled, 86% won vs 70% needed, net +16.8% on $204,966, worst day -2,112, 20 of 46 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
2026-09-24 15:58:49 ERROR Error fetching NEG_RISK_CTF events [94373591-94373592]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 15:58:52 ERROR Error fetching CTF events [94373593-94373594]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 15:59:00 INFO  [ops] form: '0x09b045ba in form' -> 'benched' | 0x09b045ba: 34 settled, 74% won vs 59% needed, net +11.5% on $13,335, worst day -333, 33 of 33 exits under 10 min
2026-09-24 15:59:06 INFO  [ops] form: '0x1985327e in form' -> 'benched' | 0x1985327e: 55 settled, 73% won vs 55% needed, net +17.3% on $21,122, worst day -535, 53 of 53 exits under 10 min
2026-09-24 16:00:04 INFO  [ops] form: '0x9f15613e in form' -> 'benched' | 0x9f15613e: 348 settled, 53% won vs 48% needed, net +10.7% on $1,037,640, worst day -31,088, 12 of 19 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
2026-09-24 16:00:24 INFO  [ops] form: '0xd970693a in form' -> 'benched' | 0xd970693a: 36 settled, 69% won vs 58% needed, net +6.9% on $13,518, worst day -324, 36 of 36 exits under 10 min
2026-09-24 16:01:57 ERROR Error fetching CTF events [94373683-94373685]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 16:06:05 ERROR Network error fetching 0xf496...fe79: 
2026-09-24 16:06:05 ERROR Network error fetching 0x0011...4333: 
2026-09-24 16:11:02 INFO  Received signal 15, shutting down...
2026-09-24 16:11:34 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 16:11:35 INFO  Bot started. Monitoring trades...
2026-09-24 16:11:52 WARNING [zset] EVICTED 0x05878ac343c1387d592042d788424412733ac40b from set Z: probation failed: 0 of 2 won, realized -99.9% on $12.80 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] evict: '0x05878ac3 in set Z' -> 'evicted (sticky)' | probation failed: 0 of 2 won, realized -99.9% on $12.80 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] probation_failed: '0x05878ac3 on probation (10 days on probation)' -> 'evicted: 0 of 2 won, realized -99.9% on $12.80 (pass needs 2 won and -10%)' | lost -6.39 on 'LoL: T1 Academy vs KT R; lost -6.40 on 'LoL: Team WE vs JD Gami | Evict is reversible: /zset readmit
2026-09-24 16:11:52 WARNING [zset] EVICTED 0x09b045baad1fbe115c70785635a261411774a3b6 from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] evict: '0x09b045ba in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] probation_failed: '0x09b045ba on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:52 WARNING [zset] EVICTED 0x1985327e5782c62362dbbdf714c423d40d8f51ab from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] evict: '0x1985327e in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:52 INFO  [ops] probation_failed: '0x1985327e on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:52 WARNING [zset] EVICTED 0x4980930da4ad1194d4f0fd5e29f17b70a42e5709 from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:53 INFO  [ops] evict: '0x4980930d in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:53 INFO  [ops] probation_failed: '0x4980930d on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:53 WARNING [zset] EVICTED 0x5213eb85fcd465c8927a8382f95dd2dc22306a35 from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:53 INFO  [ops] evict: '0x5213eb85 in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:53 INFO  [ops] probation_failed: '0x5213eb85 on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:55 WARNING [zset] EVICTED 0x57b258499f7a4cfc5043ceae57a51f7e6f529da2 from set Z: probation failed: 0 of 2 won, realized -100.0% on $12.80 (pass needs 2 won and -10%)
2026-09-24 16:11:55 INFO  [ops] evict: '0x57b25849 in set Z' -> 'evicted (sticky)' | probation failed: 0 of 2 won, realized -100.0% on $12.80 (pass needs 2 won and -10%)
2026-09-24 16:11:55 INFO  [ops] probation_failed: '0x57b25849 on probation (10 days on probation)' -> 'evicted: 0 of 2 won, realized -100.0% on $12.80 (pass needs 2 won and -10%)' | lost -6.40 on 'Counter-Strike: Bounty ; lost -6.40 on 'Dota 2:  Pipsqueak+4 vs | Evict is reversible: /zset readmit
2026-09-24 16:11:55 WARNING [zset] EVICTED 0x736539924a5602b37a03a54fc12c1cc8f98964da from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:55 INFO  [ops] evict: '0x73653992 in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:55 INFO  [ops] probation_failed: '0x73653992 on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:56 WARNING [zset] EVICTED 0xd970693a3384dc762b191707a4927ac3814bbbba from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:56 INFO  [ops] evict: '0xd970693a in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:56 INFO  [ops] probation_failed: '0xd970693a on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:11:56 WARNING [zset] EVICTED 0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c from set Z: probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:56 INFO  [ops] evict: '0xeef6ad0e in set Z' -> 'evicted (sticky)' | probation failed: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)
2026-09-24 16:11:56 INFO  [ops] probation_failed: '0xeef6ad0e on probation (10 days on probation)' -> 'evicted: 0 of 0 won, realized +0.0% on $0.00 (pass needs 2 won and -10%)' |  | Evict is reversible: /zset readmit
2026-09-24 16:12:20 WARNING [zset] ADMITTED 0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43 to set Z (+20% over 27 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-24 16:12:20 INFO  [ops] auto_admit: '0x984ffef1 not in Z' -> 'in set Z, on probation' | 30 settled paper copies, paper ROI +34.0%, trimmed +20.2%, ideal +35.0%
2026-09-24 16:12:24 INFO  [ops] form: '0x984ffef1 unknown' -> 'in form' | 0x984ffef1: 31 settled, 68% won vs 52% needed, net +53.5% on $24,914, worst day -87, 2 of 6 exits under 10 min
2026-09-24 16:12:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 16:12:28 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 16:12:29 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 16:12:30 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 16:12:31 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 16:35:37 ERROR Error fetching CTF events [94375035-94375043]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 16:36:19 INFO  Received signal 15, shutting down...
2026-09-24 16:36:56 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 16:36:57 INFO  Bot started. Monitoring trades...
2026-09-24 16:38:16 ERROR Error fetching CTF events [94375149-94375150]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 16:43:33 ERROR Network error fetching 0xf496...fe79: 
2026-09-24 16:44:04 ERROR Error fetching CTF events [94375399-94375402]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 16:44:38 ERROR Error fetching CTF events [94375423-94375425]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 16:45:02 ERROR Error fetching NEG_RISK_CTF events [94375438-94375441]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 16:56:36 ERROR [inventory] API sync failed: 
2026-09-24 16:58:22 INFO  Received signal 15, shutting down...
2026-09-24 16:58:54 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-24 16:58:55 INFO  Bot started. Monitoring trades...
2026-09-24 17:37:14 ERROR Network error fetching 0xf496...fe79: 
2026-09-24 17:37:14 ERROR Network error fetching 0xf916...e770: 
2026-09-24 17:37:14 ERROR Network error fetching 0x984f...9a43: 
2026-09-24 17:37:14 ERROR Network error fetching 0xd251...4d37: 
2026-09-24 17:53:23 ERROR Error fetching NEG_RISK_CTF events [94378147-94378153]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 17:53:53 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-24 17:53:53 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-24 17:53:54 ERROR Network error fetching 0x722a...d6ed: 
2026-09-24 18:02:17 ERROR Error fetching CTF events [94378530-94378531]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:06:04 ERROR Error fetching CTF events [94378681-94378682]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:06:04 ERROR Error fetching NEG_RISK_CTF events [94378681-94378682]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:07:00 ERROR Error fetching NEG_RISK_CTF events [94378719-94378719]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:07:05 ERROR Error fetching CTF events [94378722-94378722]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:29:00 ERROR Error fetching NEG_RISK_CTF events [94379574-94379579]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 18:31:19 ERROR Error fetching CTF events [94379666-94379672]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 18:35:15 ERROR Error fetching NEG_RISK_CTF events [94379847-94379848]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:35:18 ERROR Error fetching NEG_RISK_CTF events [94379849-94379852]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:43:13 ERROR Error fetching NEG_RISK_CTF events [94380167-94380168]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 18:48:32 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-24 18:48:53 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $38.40 / $54.00
2026-09-24 18:48:54 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $38.40 / $200.00
2026-09-24 19:03:54 ERROR Error fetching NEG_RISK_CTF events [94380994-94380995]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:06:07 ERROR Error fetching CTF events [94381083-94381084]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:06:07 ERROR Error fetching NEG_RISK_CTF events [94381083-94381084]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:07:07 ERROR Error fetching CTF events [94381123-94381124]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:16:07 ERROR Error fetching CTF events [94381482-94381484]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:26:21 ERROR Error fetching NEG_RISK_CTF events [94381893-94381893]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:31:42 ERROR Error fetching CTF events [94382106-94382107]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:31:42 ERROR Error fetching NEG_RISK_CTF events [94382106-94382107]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:35:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 19:36:05 ERROR Error fetching CTF events [94382282-94382283]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:36:05 ERROR Error fetching NEG_RISK_CTF events [94382282-94382283]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:41:05 ERROR Error fetching CTF events [94382482-94382483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:41:05 ERROR Error fetching NEG_RISK_CTF events [94382482-94382483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 19:48:19 ERROR Error fetching NEG_RISK_CTF events [94382751-94382752]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 19:50:39 ERROR Error fetching NEG_RISK_CTF events [94382845-94382845]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 19:53:01 ERROR Error fetching CTF events [94382939-94382940]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 19:53:31 ERROR Error fetching NEG_RISK_CTF events [94382939-94382940]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 20:08:16 ERROR Error fetching NEG_RISK_CTF events [94383549-94383550]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 20:16:34 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-24 20:17:02 ERROR Error fetching CTF events [94383920-94383921]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 20:17:34 ERROR Error fetching CTF events [94383942-94383942]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-24 20:17:41 ERROR Error fetching CTF events [94383946-94383946]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-23 21:54:10 TRADE [LIVE] BUY $6.40 on 'Buenos Aires 2: Francisco Comesana vs Jo' @ 0.3200, order 0x66537d0123...
2026-09-23 21:54:11 TRADE [verify] FILLED: BUY 20.00 shares on 'Buenos Aires 2: Francisco Comesana vs Jo' @ 0.3200
2026-09-24 02:55:26 TRADE [LIVE] BUY $6.40 on 'Korea Open: Yexin Ma vs Kimberly Birrell' @ 0.6600, order 0x41e2215ece...
2026-09-24 02:55:27 TRADE [verify] FILLED: BUY 9.69 shares on 'Korea Open: Yexin Ma vs Kimberly Birrell' @ 0.6600
2026-09-24 08:07:57 TRADE [LIVE] BUY $6.40 on 'Will the highest temperature in Dallas b' @ 0.8200, order 0x3326b28d62...
2026-09-24 08:07:58 TRADE [verify] FILLED: BUY 7.80 shares on 'Will the highest temperature in Dallas b' @ 0.8200
2026-09-24 11:32:03 TRADE [LIVE] BUY $6.40 on 'Game Spread: Elise Mertens (-3.5) vs Maj' @ 0.4900, order 0x066ddaa713...
2026-09-24 11:32:03 TRADE [verify] FILLED: BUY 13.06 shares on 'Game Spread: Elise Mertens (-3.5) vs Maj' @ 0.4900
2026-09-24 12:49:44 INFO  [recovery] No pending orders to recover
2026-09-24 13:03:57 TRADE [LIVE] BUY $6.40 on 'Houston Astros vs. Athletics: 1st 5 Inni' @ 0.5400, order 0x1bc7a24c2b...
2026-09-24 13:03:57 TRADE [verify] FILLED: BUY 11.85 shares on 'Houston Astros vs. Athletics: 1st 5 Inni' @ 0.5400
2026-09-24 13:13:23 INFO  [recovery] No pending orders to recover
2026-09-24 14:24:06 TRADE [LIVE] BUY $6.40 on '' @ 0.7000, order 0x1f54129ff6...
2026-09-24 14:24:07 TRADE [verify] FILLED: BUY 9.14 shares on '' @ 0.7000
2026-09-24 14:36:18 INFO  [recovery] No pending orders to recover
2026-09-24 15:02:07 INFO  [recovery] No pending orders to recover
2026-09-24 15:16:13 INFO  [recovery] No pending orders to recover
2026-09-24 15:28:20 ERROR Error fetching CTF events [94372350-94372353]: {'code': -32002, 'message': 'request timed out'}
2026-09-24 15:47:18 INFO  [recovery] No pending orders to recover
2026-09-24 15:58:13 INFO  [recovery] No pending orders to recover
2026-09-24 16:11:35 INFO  [recovery] No pending orders to recover
2026-09-24 16:36:57 INFO  [recovery] No pending orders to recover
2026-09-24 16:58:55 INFO  [recovery] No pending orders to recover
2026-09-24 18:48:54 TRADE [LIVE] BUY $6.40 on 'Will Portugal win on 2026-09-24?' @ 0.8600, order 0xed1fc1a749...
2026-09-24 18:48:54 TRADE [verify] FILLED: BUY 7.44 shares on 'Will Portugal win on 2026-09-24?' @ 0.8600
