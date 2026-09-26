# ops digest 2026-09-26T01:32:36.723965+00:00 (last 24h)

## money state
{"cash": 112.890933, "open_cost": 6.4, "equity": 119.29, "floor": 30.0, "stated": 80.0, "spend": {"date": "2026-09-26", "spent_usd": 0.0, "cap_usd": 54.0, "remaining_usd": 54.0, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 68, "tier": {"1a": 0, "1b": 12.8, "1c": 0}, "ts": 1790386156.1018941, "day": "2026-09-26"}

## arm: {"armed": true, "ts": 1789919410.9079125, "by": "telegram", "reason": "", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-26", "spent_usd": 0.0, "wallet_copies": {}, "wallet_copies_yesterday": {"0x722abb5460060870d46728bf45f66a6b1635d6ed": 1, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": 1}, "yesterday": "2026-09-25", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x722abb5460060870d46728bf45f66a6b1635d6ed": {"wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed", "tier": "1b", "ts": 1789491938.939273, "source": "telegram-gate"}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"wallet": "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333", "tier": "1b", "ts": 1789752841.6491823, "source": "telegram-gate"}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"wallet": "0xf49614e63fb15383d4a9b717a1be03ad2410fe79", "tier": "1b", "ts": 1789827877.6900246, "source": "telegram-gate"}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"wallet": "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770", "tier": "1b", "ts": 1789992497.9469755, "source": "telegram-gate"}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"wallet": "0xd25156e222c9b907b128e27c36821fdb41db4d37", "tier": "1b", "ts": 1790166550.4519851, "source": "telegram-gate"}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43", "tier": "1b", "ts": 1790266340.2195778, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [12.8, 2], "1c": [0, 0]}
## probation: {"0x722abb5460060870d46728bf45f66a6b1635d6ed": {"since": 1789491935.7564917, "settled": 0, "held_said": true}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"since": 1789752828.6614223, "settled": 0}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"since": 1789827868.9550335, "settled": 0}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"since": 1789992496.5955625, "settled": 0}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"since": 1790166548.6465027, "settled": 0}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"since": 1790266317.6788435, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
benched  0x00110b8e: 215 settled, 85% won vs 69% needed, net +16.9% on $199,513, worst day -2,112, 22 of 43 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x3f3aa700: 222 settled, 50% won vs 54% needed, net -0.3% on $654,838, worst day -24,321, 1 of 6 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x722abb54: 84 settled, 77% won vs 75% needed, net +3.9% on $152,696, worst day -3,391, 7 of 68 exits under 10 min
in form  0x984ffef1: 32 settled, 72% won vs 53% needed, net +56.3% on $23,930, worst day -87, 3 of 8 exits under 10 min
benched  0x9f15613e: 341 settled, 52% won vs 48% needed, net +8.1% on $1,061,275, worst day -31,088, 11 of 16 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xd25156e2: 66 settled, 67% won vs 50% needed, net +36.8% on $36,266, worst day -1,488, 3 of 27 exits under 10 min (capped: 9.5 of 14 days read, 5500 rows)
benched  0xf49614e6: 66 settled, 50% won vs 50% needed, net +10.8% on $230,471, worst day -11,771, 4 of 10 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xf9168343: 53 settled, 55% won vs 48% needed, net +2.8% on $146,637, worst day -6,320, 2 of 33 exits under 10 min
benched  0xfd3e6449: 67 settled, 64% won vs 71% needed, net -2.7% on $48,555, worst day -2,632, 19 of 22 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
two clocks: 81 matched fills over 1.0 d, api lag p50 17.7s, chain lag p50 2.9s, chain earlier by 13.8s at the median; api-only 9, chain-only 708, replayed rows 0; CHAIN IS PRIMARY
⏱ api lag cost, last 7d (estimate): +19.49 USD over 3194 fills at $6.40 each, +0.000 USD a fill at the median, chain earlier by 13.7s

## watcher (21 wakes in 24h)
{"ts": 1790316060.064088, "kind": "analyst", "woke_because": "daily check of min150", "concluded": "control differs from book B by -7.5 pp on 65 copies (tolerance 1.5): the harness, not the idea, is what moved", "did": "exp min150 void: control differs from book B by -7.5 pp on 65 copies (tolerance 1.5): the harness, not the idea, is what moved", "cost_usd": 0.0}
{"ts": 1790316060.064088, "kind": "analyst", "woke_because": "daily study", "concluded": "At a 5 per day wallet cap versus the live 3, over book B's own rows, how many extra copies enter and what do the ones the 3 cap turned away actually earn?", "did": "study 2026-09-25-wallet_cap-178163d7 frozen: wallets in 32 -> 34 (stay 32, enter 2, leave 0); copies 3840 -> 2956; ROI at their price +9.0% -> +1
{"ts": 1790316060.064088, "kind": "analyst", "woke_because": "daily study", "concluded": "-7.5pp is how far min150's control drifted from book B on 65 copies at a 1.5pp tolerance, so the paper experiment harness cannot reproduce its own control and no experiment verdict is trustworthy until the control replay is made deterministic; hold new experiments until it is fixed.", "did": "noted", "cost_us
{"ts": 1790316060.064088, "kind": "analyst", "woke_because": "study 2026-09-25-wallet_cap-178163d7", "concluded": "Cutting the wallet cap from 25 to 5 drops 884 copies (3840 to 2956) and lifts ROI at their price by +2.8pp (+9.0% to +11.8%), so the late daily tail is dilutive. But live is already 3, tighter than both arms, so this run says nothing about the 3 vs 5 copies the question asked and any 
{"ts": 1790316060.064088, "kind": "analyst", "woke_because": "daily study", "concluded": "Study wallet cap 3 vs 5 (the 3 cap turned away +32.93 of winners); hold experiments, the harness control drifted -7.5pp from book B.", "did": "3 proposal(s): study 2026-09-25-wallet_cap-178163d7 frozen: wallets in 32 -; noted; concluded; one question the menu cannot compute noted", "cost_usd": 0.50288}
{"ts": 1790338890.2227454, "kind": "note", "woke_because": "5f7bb5f89b09", "concluded": "A CLOB Server disconnected during live placement returned no order id, so the bot could not confirm whether the $6.40 copy:1b order was accepted, and the daily-cap handler kept the reservation as the conservative choice. This is the designed ambiguous-fate branch, not a failure: the budget stays charged so the
{"ts": 1790341080.59767, "kind": "analyst", "woke_because": "supervise", "concluded": "requeued min150 as min150-r1", "did": "requeued min150 as min150-r1", "cost_usd": 0.0}
{"ts": 1790341080.59767, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150-r1 (pid 7, first start since this supervisor came up)", "did": "started min150-r1 (pid 7, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790341202.3576975, "kind": "nothing", "woke_because": "962fd1d59e01", "concluded": "The line that woke me is the bot's own routine loss-streak escalation being delivered successfully, an INFO event, not an error. The bot detected the streak grew from 4 to 7 losing copies and its alert path already sent that to the owner (escalation_delivered: sent), so he already knows. A losing streak is 
{"ts": 1790341504.9359877, "kind": "note", "woke_because": "1d84f68e4a14, 705df184a49d", "concluded": "A transient Polymarket API network failure caused this: the client logged 'Server disconnected' twice, so the order POST raised a PolyApiException with status_code=None and the executor got None back. This landed in the middle of a broader API rough patch right now (Server disconnected x24, reque
{"ts": 1790342643.9407513, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150-r1 (pid 6, first start since this supervisor came up)", "did": "started min150-r1 (pid 6, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790343245.2721663, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150-r1 (pid 7, first start since this supervisor came up)", "did": "started min150-r1 (pid 7, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790343885.1950855, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150-r1 (pid 67, first start since this supervisor came up)", "did": "started min150-r1 (pid 67, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790346046.2132301, "kind": "nothing", "woke_because": "7a8d58f20915", "concluded": "The cause is a transient network read error while fetching a trader address, logged with an empty exception string so str(e) rendered nothing after the colon. It is the same family as the known 6eca45f47973 'Server disconnected' errors, which are hitting the flaky Polymarket API right now alongside the pric
{"ts": 1790347551.8864553, "kind": "note", "woke_because": "6fbcddbc9dfb", "concluded": "The chain RPC rejected a NEG_RISK_CTF event query for block range 94428207-94428208 with code -32000 invalid block range params, a provider side read error. This is on the on-chain event read path, not the order placement or sizing path, and it happened once. The provider most likely had not yet indexed that 2
{"ts": 1790348314.5935838, "kind": "note", "woke_because": "dcba498fc237", "concluded": "The chain RPC node rejected a tiny forward block range (94428704-94428706) with -32000 invalid block range params, which is what a node returns when the requested toBlock sits at or ahead of its own synced head. Both the CTF and NEG_RISK_CTF fetches failed at the same second on the identical range, which is th
{"ts": 1790351832.0916538, "kind": "nothing", "woke_because": "41cab7e764a5", "concluded": "The cause is a single transient HTTP read timeout from the Polymarket CLOB client, the same class of API flakiness as the Server disconnected fingerprint. It is one hit on a generic request wrapper, not on a confirmed order placement, and the money path stays verifiable: TRADE [verify] FILLED lines are curr
{"ts": 1790355818.2363145, "kind": "nothing", "woke_because": "ca12f2f09597", "concluded": "The cause is a transient upstream disconnect: Polymarket closed the connection while the bot was reading CTF events, a pure read path with no order placement, sizing or verification attached. It fired only twice and sits inside a broad wave of the same upstream instability this hour (py_clob_client_v2 serve
{"ts": 1790356091.7305198, "kind": "nothing", "woke_because": "001dacd732e7", "concluded": "The cause is routine probation bookkeeping: trader 0x722abb54 was just benched and put on probation, and with 0 live copies settled against the 2 the bar needs it is held as untested, not failed. This fingerprint is new only because this trader entered probation this cycle, matching the form and probation_h
{"ts": 1790364989.5143719, "kind": "nothing", "woke_because": "1bd07071cf73", "concluded": "The cause is a single transient RemoteDisconnected on the onchain poll, one blip inside a wider network storm hitting every Polymarket endpoint at the same minute (CTF events, clob price, auth, negrisk all show RemoteDisconnected or timeouts in the same window). This is remote infrastructure closing connect
{"ts": 1790378100.0295238, "kind": "nothing", "woke_because": "13ad3e5ddfe8", "concluded": "A single upstream disconnect caused one inventory API sync to fail. This is one hit of the same 'Server disconnected without sending a response' wave hitting every path right now (6eca45f47973 x8, 6c813168939b x37, 54ac26fb3ff1 x76), so it is transient Polymarket API flakiness, not a bot fault. Inventory sy
## live limits (owner's number, and the analyst's where one is in force)
LIVE_MAX_PER_WALLET_DAY: 3 (owner) band 1..3
FETCH_INTERVAL: 3.0 (owner) band 2..5
OPS_REARM_CLEAR_S: 900.0 (owner) band 600.0..1800.0
OPS_REARM_MAX_PER_DAY: 3 (owner) band 1..3
FORM_DAYS: 14.0 (owner) band 7.0..21.0
## book B at each slice floor (raw numbers; the gate reads the one marked)
b300 (floor $300): 7416 settled, 248 open, realized +2.1%, at their price +3.0% (net -7.8%), win rate 57%, feeds the Z gate
b150 (floor $150): 219 settled, 38 open, realized -9.7%, at their price -8.8% (net -19.5%), win rate 52%
b100 (floor $100): 269 settled, 65 open, realized +1.4%, at their price +2.4% (net -8.2%), win rate 52%
## near the Z door (30 wallets within 2 fails; 8 pass and wait)
0x00110b8e: 1 fail(s): not a scalper at our latency (scalper: 51% of exits within 10 min; uncopyable at our latency)
0x10658d37: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (26 clean (of 26 all-time))
0x19585131: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (21 clean (of 21 all-time))
0x37c1ff27: 1 fail(s): promotion floor still holds (copy ROI +3% < floor +10%)
0x3968f7c9: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (17 clean (of 17 all-time))
0x4a3f86ed: 1 fail(s): promotion floor still holds (copy ROI +4% < floor +10%)
0x57b25849: 1 fail(s): promotion floor still holds (copy ROI +7% < floor +10%; 2nd-half ROI -10% < -10% (edge decaying))
0x8342720d: 1 fail(s): still positive with its best 3 copies deleted (-0% over 45 copies with its best 3 deleted)
0x91c7d990: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (17 clean (of 17 all-time))
0x9f15613e: 1 fail(s): not a scalper at our latency (scalper: 69% of exits within 10 min; uncopyable at our latency)
0xcd741947: 1 fail(s): still positive with its best 3 copies deleted (-6% over 42 copies with its best 3 deleted)
0xf49614e6: 1 fail(s): not a scalper at our latency (scalper: 40% of exits within 10 min; uncopyable at our latency)
## experiments (the analyst's cards; one live at a time)
min150-r1        live   slice floor 300 to 150                             no check  (min150-r1 <- min150, study 2026-09-24-min_usd-cdc749c5)
min150           void   slice floor 300 to 150                             n 128 -1.9 pp  (min150 <- study 2026-09-24-min_usd-cdc749c5)
{"day": "2026-09-25", "id": "min150", "event": "void", "why": "control differs from book B by -7.5 pp on 65 copies (tolerance 1.5): the harness, not the idea, is what moved", "delta_pp": -1.86, "n": 128}
{"day": "2026-09-25", "id": "min150-r1", "event": "queued"}
{"day": "2026-09-25", "id": "min150-r1", "event": "requeued", "why": "control differs from book B by -7.5 pp on 65 copies (tolerance 1.5): the harness, not the idea, is what moved"}
{"day": "2026-09-25", "id": "min150-r1", "event": "live"}
study 2026-09-24-first_entry-152981e2: wallets in 18 -> 18 (stay 18, enter 0, leave 0); copies 3276 -> 3276; ROI at their price +3.5% -> +3.5%
study 2026-09-24-min_usd-cdc749c5: wallets in 19 -> 20 (stay 15, enter 5, leave 4); copies 3567 -> 5216; ROI at their price +2.6% -> +3.7%
study 2026-09-25-wallet_cap-178163d7: wallets in 32 -> 34 (stay 32, enter 2, leave 0); copies 3840 -> 2956; ROI at their price +9.0% -> +11.8%
## questions the study menu could not compute (last 7 days)
2026-09-24 after study 2026-09-24-first_entry-152981e2: With first_entry_only=false as the baseline (copying every buy), how many copies collapse to one per market when we switch it on, and does the +3.5% ROI hold? (missing: This run set both the from and to arms to first_entry_only=true, so there is no every-buy baseline in the frozen table to difference against.)
2026-09-25 after study 2026-09-25-wallet_cap-178163d7: What do the copies in wallet-day slots 4 and 5 actually earn, the ones the live cap of 3 turns away but a cap of 5 would admit? (missing: This run baselined at cap 25 rather than the live 3, so its rows cannot isolate the marginal ROI of the slot 4 and 5 copies; that needs a study framed from {cap:3} to {cap:5}.)
## fingerprints (30 shown)
dcba498fc237 x77 last 0.0h ago [open: 77 hits, no action yet] :: ERROR Error fetching CTF events [NN]: {'S': N, 'S': 'S'}
6fbcddbc9dfb x52 last 0.0h ago [open: 52 hits, no action yet] :: ERROR Error fetching NEG_RISK_CTF events [NN]: {'S': N, 'S': 'S'}
54ac26fb3ff1 x77 last 0.6h ago [open: 77 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/price body={'S':'S'}
6c813168939b x44 last 0.6h ago [open: 44 hits, no action yet] :: ERROR [py_clob_client_v2] request error: Server disconnected
41cab7e764a5 x7 last 0.6h ago [open: 7 hits, no action yet] :: ERROR [py_clob_client_v2] request error: The read operation timed out
13ad3e5ddfe8 x1 last 2.3h ago [open: 1 hits, no action yet] :: ERROR [inventory] API sync failed: Server disconnected without sending a response.
6eca45f47973 x8 last 2.9h ago [open: 8 hits, no action yet] :: ERROR Network error fetching <hex>: Server disconnected without sending a response.
7a8d58f20915 x6 last 2.9h ago [open: 6 hits, no action yet] :: ERROR Network error fetching <hex>:
1bd07071cf73 x2 last 3.8h ago [open: 2 hits, no action yet] :: ERROR Onchain poll error: ('S', RemoteDisconnected('S'))
ca12f2f09597 x6 last 5.9h ago [open: 6 hits, no action yet] :: ERROR Error fetching CTF events [NN]: ('S', RemoteDisconnected('S'))
c6d91d798e54 x17 last 8.4h ago [open: 17 hits, no action yet] :: INFO [tiered-risk] tier Nb: released $N of exposure from resolved or closed positions | open now: $N
001dacd732e7 x1 last 8.4h ago [open: 1 hits, no action yet] :: INFO [ops] probation_held: 'S' -> 'S' | untested is not failed; the clock keeps running
9d498e122ffb x5 last 9.3h ago [open: 5 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N, N of N exits under N min
69fd3dc7d27e x21 last 10.6h ago [open: 21 hits, no action yet] :: INFO [daily-cap] +$N (copy:Nb) reserved | total today $N / $N
eb7da12386c6 x19 last 10.6h ago [open: 19 hits, no action yet] :: TRADE [LIVE] BUY $N on 'S' @ N, order <hex>...
a77088f7944a x19 last 10.6h ago [open: 19 hits, no action yet] :: INFO [tiered-risk] Recorded tier Nb placement: $N | open: $N / $N
d7140f640d29 x18 last 10.6h ago [open: 18 hits, no action yet] :: TRADE [verify] FILLED: BUY N shares on 'S' @ N
6f12d4998994 x21 last 11.9h ago [open: 21 hits, no action yet] :: INFO [recovery] No pending orders to recover
6b829965c182 x21 last 11.9h ago [open: 21 hits, no action yet] :: INFO Bot started. Monitoring trades...
9d8a6d2794ec x15 last 11.9h ago [open: 15 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/auth/api-key body={'S':'S'}
c47d62e70341 x21 last 11.9h ago [open: 21 hits, no action yet] :: INFO Received signal N, shutting down...
5f7bb5f89b09 x2 last 12.5h ago [open: 2 hits, no action yet] :: INFO [daily-cap] $N reservation kept: the post's fate is ambiguous (no order id)
1d84f68e4a14 x1 last 12.5h ago [open: 1 hits, no action yet] :: ERROR [exec] Order placement failed: PolyApiException[status_code=None, error_message=Request exception!]
705df184a49d x1 last 12.5h ago [open: 1 hits, no action yet] :: ERROR [exec] Order placement returned None for 'S': exchange error: Request exception!
962fd1d59e01 x1 last 12.5h ago [open: 1 hits, no action yet] :: INFO [ops] escalation_delivered: 'S' -> 'S' | Loss streak is N losing copies in a row, up from N a week ago. The bot's o
34253fa6334e x5 last 17.5h ago [open: 5 hits, no action yet] :: INFO [AB-RACE] rehearsal line sent, real-money line sent
2497cd50ff7d x3 last 21.9h ago [open: 3 hits, no action yet] :: INFO [ops] settled: 'S' -> 'S' | lost N on 'S' (<hex>, tier Nb)
c3db66a087f7 x3 last 33.3h ago [open: 3 hits, no action yet] :: WARNING [zset] ADMITTED <hex> to set Z (N over N copies with its best N deleted). Real money may now follow it once arme
790247505aab x3 last 33.3h ago [open: 3 hits, no action yet] :: INFO [ops] auto_admit: 'S' -> 'S' | N settled paper copies, paper ROI N, trimmed N, ideal N
b04bf1a60c1d x9 last 33.3h ago [open: 9 hits, no action yet] :: WARNING [zset] EVICTED <hex> from set Z: probation failed: N of N won, realized N on $N (pass needs N won and N)

## ledger (8 rows)
{"ts": 1790307460.8944914, "day": "2026-09-25", "kind": "settled", "before": "open $6.40", "after": "paid $0.00", "detail": "lost -6.40 on 'Falcons vs. Packers' (0x9f15613e, tier 1b)", "push": null, "token_id": "114415763702250973760299499587430450894909671709658162852834453684441658587440", "wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "pnl": -6.4, "won": false, "cost": 6.4}
{"ts": 1790316060.064088, "day": "2026-09-25", "kind": "analyst_study", "before": "2026-09-25-wallet_cap-178163d7", "after": "wallets in 32 -> 34 (stay 32, enter 2, leave 0); copies 3840 -> 2956; ROI at their price +9.0% -> +11.8%", "detail": "estimate: 40 of 183 wallets studied (most settled first); over book B's own settled rows at their price; in = positive at their price on at least 10 settled cop", "push": "BOT"}
{"ts": 1790341080.423772, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790341088.5600715, "day": "2026-09-25", "kind": "escalation_delivered", "before": "routine escalation", "after": "sent", "detail": "Loss streak is 7 losing copies in a row, up from 4 a week ago. The bot's only alert fired once, at 4, on Sep 18 (bankrol", "push": "BOT"}
{"ts": 1790342643.4500165, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790343524.3963003, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790352581.6513798, "day": "2026-09-25", "kind": "form", "before": "0x722abb54 in form", "after": "benched", "detail": "0x722abb54: 86 settled, 78% won vs 75% needed, net +6.1% on $164,749, worst day -3,391, 7 of 70 exits under 10 min", "push": "WALLET", "wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed"}
{"ts": 1790355972.0362878, "day": "2026-09-25", "kind": "probation_held", "before": "0x722abb54 on probation (10 days on probation)", "after": "held: 0 live copy(ies) settled, under the 2 the bar needs", "detail": "untested is not failed; the clock keeps running", "push": null, "wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed"}

## important lines (393)
2026-09-25 01:33:40 ERROR Error fetching NEG_RISK_CTF events [94396581-94396586]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 01:36:58 ERROR Error fetching NEG_RISK_CTF events [94396689-94396691]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 01:56:36 ERROR Error fetching NEG_RISK_CTF events [94397498-94397502]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:16:07 ERROR Error fetching CTF events [94398283-94398284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:16:07 ERROR Error fetching NEG_RISK_CTF events [94398283-94398284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:16:22 ERROR Error fetching CTF events [94398293-94398294]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:17:29 ERROR Error fetching NEG_RISK_CTF events [94398338-94398339]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:21:14 ERROR Error fetching CTF events [94398488-94398489]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:22:05 ERROR Error fetching CTF events [94398522-94398523]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:26:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 02:26:09 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $6.40 / $54.00
2026-09-25 02:26:10 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $38.40 / $200.00
2026-09-25 02:26:13 ERROR Error fetching CTF events [94398687-94398688]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:26:40 ERROR Error fetching CTF events [94398705-94398706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:26:59 ERROR Error fetching CTF events [94398718-94398719]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:33:55 ERROR Error fetching NEG_RISK_CTF events [94398975-94398976]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 02:40:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 02:43:57 ERROR Error fetching CTF events [94399397-94399398]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:44:13 ERROR Error fetching NEG_RISK_CTF events [94399407-94399408]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:45:08 ERROR Error fetching NEG_RISK_CTF events [94399444-94399445]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:49:59 ERROR Error fetching CTF events [94399638-94399639]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:50:16 ERROR Error fetching NEG_RISK_CTF events [94399650-94399650]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:50:29 ERROR Error fetching NEG_RISK_CTF events [94399658-94399659]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:52:23 ERROR Error fetching CTF events [94399734-94399735]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:56:06 ERROR Error fetching CTF events [94399882-94399883]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:57:22 ERROR Error fetching NEG_RISK_CTF events [94399933-94399934]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:57:29 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $32.00
2026-09-25 03:00:01 ERROR Error fetching CTF events [94400037-94400040]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:00:01 ERROR Error fetching NEG_RISK_CTF events [94400037-94400040]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:03:17 ERROR Error fetching NEG_RISK_CTF events [94400170-94400171]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:16:32 ERROR Error fetching NEG_RISK_CTF events [94400700-94400700]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:16:51 ERROR Error fetching CTF events [94400712-94400713]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:20:21 ERROR Error fetching CTF events [94400853-94400853]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:20:37 ERROR Error fetching CTF events [94400864-94400864]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:21:38 ERROR Error fetching CTF events [94400904-94400905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:21:38 ERROR Error fetching NEG_RISK_CTF events [94400904-94400905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:31:38 ERROR Error fetching CTF events [94401304-94401305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:31:38 ERROR Error fetching NEG_RISK_CTF events [94401304-94401305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:35:19 ERROR Error fetching CTF events [94401451-94401452]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:36:41 ERROR Error fetching CTF events [94401506-94401507]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:37:40 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $25.60
2026-09-25 03:37:40 INFO  [ops] settled: 'open $6.40' -> 'paid $0.00' | lost -6.40 on 'Falcons vs. Packers' (0x9f15613e, tier 1b)
2026-09-25 03:40:05 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 03:40:33 ERROR Error fetching CTF events [94401661-94401662]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:41:39 ERROR Error fetching CTF events [94401705-94401706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:41:40 ERROR Error fetching NEG_RISK_CTF events [94401705-94401706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:43:01 ERROR Error fetching CTF events [94401756-94401760]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:43:03 ERROR Error fetching CTF events [94401761-94401761]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:43:03 ERROR Error fetching NEG_RISK_CTF events [94401761-94401761]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:45:26 ERROR Error fetching NEG_RISK_CTF events [94401856-94401857]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:56:35 ERROR Error fetching CTF events [94402302-94402303]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 03:56:35 ERROR Error fetching NEG_RISK_CTF events [94402302-94402303]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:01:32 ERROR Error fetching CTF events [94402500-94402501]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:01:32 ERROR Error fetching NEG_RISK_CTF events [94402500-94402501]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:01:53 ERROR Error fetching CTF events [94402514-94402515]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:15 ERROR Error fetching NEG_RISK_CTF events [94402729-94402729]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:17 ERROR Error fetching CTF events [94402730-94402731]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:17 ERROR Error fetching NEG_RISK_CTF events [94402730-94402731]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:19 ERROR Error fetching CTF events [94402732-94402732]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:19 ERROR Error fetching NEG_RISK_CTF events [94402732-94402732]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:22 ERROR Error fetching NEG_RISK_CTF events [94402733-94402734]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:28 ERROR Error fetching CTF events [94402738-94402738]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:28 ERROR Error fetching NEG_RISK_CTF events [94402738-94402738]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:30 ERROR Error fetching CTF events [94402739-94402739]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:35 ERROR Error fetching CTF events [94402742-94402742]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:37 ERROR Error fetching NEG_RISK_CTF events [94402743-94402744]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:39 ERROR Error fetching CTF events [94402745-94402745]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:07:43 ERROR Error fetching CTF events [94402747-94402748]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:11:15 ERROR Error fetching CTF events [94402889-94402890]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:13:31 ERROR Error fetching NEG_RISK_CTF events [94402979-94402980]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:15:07 ERROR Error fetching NEG_RISK_CTF events [94403043-94403044]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:20:43 ERROR Error fetching CTF events [94403267-94403268]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:21:38 ERROR Error fetching CTF events [94403304-94403304]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:21:38 ERROR Error fetching NEG_RISK_CTF events [94403304-94403304]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:27:31 ERROR Error fetching CTF events [94403539-94403540]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:45:58 ERROR Error fetching CTF events [94404278-94404278]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:46:41 ERROR Error fetching NEG_RISK_CTF events [94404306-94404307]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:56:07 ERROR Error fetching CTF events [94404683-94404684]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 04:56:07 ERROR Error fetching NEG_RISK_CTF events [94404683-94404684]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 05:03:53 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $19.20
2026-09-25 05:05:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 05:42:02 ERROR Error fetching CTF events [94406520-94406521]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 05:58:47 ERROR Error fetching CTF events [94407190-94407191]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:09:17 ERROR Error fetching CTF events [94407610-94407611]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:10:46 ERROR Error fetching NEG_RISK_CTF events [94407669-94407670]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:12:21 ERROR Error fetching CTF events [94407713-94407713]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:12:53 ERROR Error fetching NEG_RISK_CTF events [94407714-94407734]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:17:57 ERROR Error fetching CTF events [94407937-94407937]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:19:06 ERROR Error fetching NEG_RISK_CTF events [94407983-94407983]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:20:13 ERROR Error fetching CTF events [94408047-94408048]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:21:20 ERROR Error fetching CTF events [94408092-94408093]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:23:30 ERROR Error fetching CTF events [94408159-94408159]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:31:41 ERROR Error fetching NEG_RISK_CTF events [94408506-94408507]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:36:47 ERROR Error fetching NEG_RISK_CTF events [94408710-94408711]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:42:28 ERROR Error fetching CTF events [94408937-94408938]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:49:21 ERROR Error fetching CTF events [94409193-94409193]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 06:50:55 ERROR Error fetching CTF events [94409275-94409276]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:50:55 ERROR Error fetching NEG_RISK_CTF events [94409275-94409276]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:52:01 ERROR Error fetching NEG_RISK_CTF events [94409319-94409320]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 06:53:15 ERROR Error fetching CTF events [94409349-94409350]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 07:01:40 ERROR Error fetching CTF events [94409705-94409706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:01:40 ERROR Error fetching NEG_RISK_CTF events [94409705-94409706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:13:40 ERROR Error fetching CTF events [94410185-94410186]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:14:35 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $12.80
2026-09-25 07:26:39 ERROR Error fetching CTF events [94410705-94410706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:26:39 ERROR Error fetching NEG_RISK_CTF events [94410705-94410706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:34:29 ERROR Error fetching NEG_RISK_CTF events [94411018-94411019]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 07:44:59 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 08:00:11 INFO  [AB-RACE] rehearsal line sent, real-money line sent
2026-09-25 08:08:22 ERROR Error fetching NEG_RISK_CTF events [94412373-94412374]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:19:13 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 08:19:36 ERROR Error fetching NEG_RISK_CTF events [94412823-94412823]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:28:00 ERROR Error fetching CTF events [94413158-94413159]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:28:05 ERROR Error fetching CTF events [94413162-94413162]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:28:05 ERROR Error fetching NEG_RISK_CTF events [94413162-94413162]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:28:07 ERROR Error fetching CTF events [94413163-94413164]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:28:22 ERROR Error fetching NEG_RISK_CTF events [94413173-94413174]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:32:05 ERROR Error fetching NEG_RISK_CTF events [94413322-94413323]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:32:55 ERROR Error fetching NEG_RISK_CTF events [94413355-94413356]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:40:42 ERROR Error fetching CTF events [94413667-94413667]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:51:50 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 08:56:06 ERROR Error fetching CTF events [94414282-94414283]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:01:44 ERROR Error fetching CTF events [94414508-94414509]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:01:44 ERROR Error fetching NEG_RISK_CTF events [94414508-94414509]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:05:22 ERROR Error fetching NEG_RISK_CTF events [94414653-94414654]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:07:24 ERROR Error fetching CTF events [94414735-94414735]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:21:25 ERROR Error fetching CTF events [94415295-94415296]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:21:25 ERROR Error fetching NEG_RISK_CTF events [94415295-94415296]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:41:17 ERROR Error fetching NEG_RISK_CTF events [94416090-94416091]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:46:07 ERROR Error fetching CTF events [94416283-94416284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:46:07 ERROR Error fetching NEG_RISK_CTF events [94416283-94416284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:46:22 ERROR Error fetching CTF events [94416293-94416294]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:47:54 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 09:48:07 ERROR Error fetching NEG_RISK_CTF events [94416363-94416364]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:52:14 ERROR Error fetching CTF events [94416528-94416529]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:52:14 ERROR Error fetching NEG_RISK_CTF events [94416528-94416529]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 09:53:16 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 09:59:17 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 10:02:05 ERROR Error fetching CTF events [94416918-94416923]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:02:06 ERROR Error fetching NEG_RISK_CTF events [94416918-94416923]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:02:12 ERROR Error fetching CTF events [94416924-94416927]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:02:16 ERROR Error fetching CTF events [94416928-94416929]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:07:39 ERROR [inventory] API sync failed: 
2026-09-25 10:08:55 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 10:16:25 ERROR Error fetching NEG_RISK_CTF events [94417468-94417474]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 10:20:58 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-25 10:20:58 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-25 10:20:58 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-25 10:24:51 ERROR Error fetching NEG_RISK_CTF events [94417807-94417812]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 10:29:28 ERROR Error fetching NEG_RISK_CTF events [94417998-94417998]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 10:30:17 ERROR Error fetching CTF events [94418026-94418030]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 10:39:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 10:39:42 ERROR [inventory] API sync failed: 
2026-09-25 10:48:08 ERROR Error fetching CTF events [94418764-94418765]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:54:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 11:05:02 ERROR Error fetching CTF events [94419440-94419441]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 11:06:10 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 11:31:06 ERROR Error fetching CTF events [94420482-94420483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 11:31:06 ERROR Error fetching NEG_RISK_CTF events [94420482-94420483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 11:56:06 ERROR Error fetching NEG_RISK_CTF events [94421482-94421483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 11:59:24 ERROR Error fetching CTF events [94421594-94421595]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 12:05:41 ERROR Error fetching CTF events [94421846-94421846]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 12:07:03 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 12:12:25 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 12:19:29 ERROR Error fetching NEG_RISK_CTF events [94422418-94422419]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:19:41 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $12.80 / $54.00
2026-09-25 12:19:41 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 12:19:41 ERROR [exec] Order placement failed: PolyApiException[status_code=None, error_message=Request exception!]
2026-09-25 12:19:41 INFO  [daily-cap] $6.40 reservation kept: the post's fate is ambiguous (no order id)
2026-09-25 12:19:41 ERROR [exec] Order placement returned None for '': exchange error: Request exception!
2026-09-25 12:21:06 ERROR Error fetching CTF events [94422482-94422483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:21:06 ERROR Error fetching NEG_RISK_CTF events [94422482-94422483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:31:07 ERROR Error fetching CTF events [94422879-94422884]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:31:07 ERROR Error fetching NEG_RISK_CTF events [94422879-94422884]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:31:42 ERROR Error fetching NEG_RISK_CTF events [94422907-94422908]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:36:05 ERROR Error fetching NEG_RISK_CTF events [94423082-94423083]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:40:00 ERROR Error fetching NEG_RISK_CTF events [94423219-94423219]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 12:41:38 ERROR Error fetching CTF events [94423304-94423305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:41:38 ERROR Error fetching NEG_RISK_CTF events [94423304-94423305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:44:24 ERROR Error fetching CTF events [94423414-94423415]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 12:57:29 INFO  Received signal 15, shutting down...
2026-09-25 12:57:54 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-25 12:57:54 INFO  Bot started. Monitoring trades...
2026-09-25 12:58:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 12:58:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 12:58:09 INFO  [ops] escalation_delivered: 'routine escalation' -> 'sent' | Loss streak is 7 losing copies in a row, up from 4 a week ago. The bot's only alert fired once, at 4, on Sep 18 (bankrol
2026-09-25 13:02:43 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:02:45 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:03:05 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $19.20 / $54.00
2026-09-25 13:03:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 13:03:07 ERROR [exec] Order placement failed: PolyApiException[status_code=None, error_message=Request exception!]
2026-09-25 13:03:07 INFO  [daily-cap] $6.40 reservation kept: the post's fate is ambiguous (no order id)
2026-09-25 13:03:07 ERROR [exec] Order placement returned None for '': exchange error: Request exception!
2026-09-25 13:07:59 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:13:21 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:13:22 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:19:13 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:21:41 ERROR Network error fetching 0xd251...4d37: Server disconnected without sending a response.
2026-09-25 13:21:41 ERROR Network error fetching 0xf916...e770: Server disconnected without sending a response.
2026-09-25 13:21:41 ERROR Network error fetching 0x984f...9a43: Server disconnected without sending a response.
2026-09-25 13:23:28 INFO  Received signal 15, shutting down...
2026-09-25 13:24:05 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-25 13:24:06 INFO  Bot started. Monitoring trades...
2026-09-25 13:27:54 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 13:38:12 INFO  Received signal 15, shutting down...
2026-09-25 13:38:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-25 13:38:50 INFO  Bot started. Monitoring trades...
2026-09-25 14:19:32 ERROR Network error fetching 0x984f...9a43: 
2026-09-25 14:19:33 ERROR Network error fetching 0xf496...fe79: Server disconnected without sending a response.
2026-09-25 14:44:13 ERROR Error fetching NEG_RISK_CTF events [94428207-94428208]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 14:49:59 ERROR Error fetching NEG_RISK_CTF events [94428438-94428439]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 14:52:53 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $25.60 / $54.00
2026-09-25 14:52:54 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $19.20 / $200.00
2026-09-25 14:56:40 ERROR Error fetching CTF events [94428704-94428706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 14:56:40 ERROR Error fetching NEG_RISK_CTF events [94428704-94428706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 15:26:38 ERROR Error fetching CTF events [94429904-94429905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 15:26:38 ERROR Error fetching NEG_RISK_CTF events [94429904-94429905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 15:34:57 ERROR Error fetching CTF events [94430217-94430217]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 15:57:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 15:57:06 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 15:57:51 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 16:10:06 INFO  [ops] form: '0x722abb54 in form' -> 'benched' | 0x722abb54: 86 settled, 78% won vs 75% needed, net +6.1% on $164,749, worst day -3,391, 7 of 70 exits under 10 min
2026-09-25 16:11:09 ERROR Error fetching CTF events [94431684-94431685]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:11:09 ERROR Error fetching NEG_RISK_CTF events [94431684-94431685]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:14:30 ERROR Error fetching CTF events [94431819-94431820]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:14:30 ERROR Error fetching NEG_RISK_CTF events [94431819-94431820]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:21:06 ERROR Error fetching CTF events [94432082-94432083]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:23:40 ERROR Error fetching NEG_RISK_CTF events [94432186-94432186]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:23:53 ERROR Error fetching CTF events [94432194-94432194]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:30:58 ERROR Error fetching NEG_RISK_CTF events [94432477-94432478]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:33:58 ERROR Error fetching CTF events [94432597-94432598]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:44:14 ERROR Error fetching CTF events [94433008-94433009]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:44:14 ERROR Error fetching NEG_RISK_CTF events [94433008-94433009]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 16:50:58 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 16:51:03 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 17:01:56 ERROR Error fetching CTF events [94433716-94433716]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 17:02:00 ERROR Error fetching CTF events [94433719-94433719]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 17:06:12 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $12.80
2026-09-25 17:06:12 INFO  [ops] probation_held: '0x722abb54 on probation (10 days on probation)' -> 'held: 0 live copy(ies) settled, under the 2 the bar needs' | untested is not failed; the clock keeps running
2026-09-25 17:17:46 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 17:17:51 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 17:21:05 ERROR Error fetching CTF events [94434482-94434483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:32:04 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 17:32:09 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 17:44:41 ERROR Error fetching CTF events [94435406-94435406]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 17:47:47 ERROR Error fetching NEG_RISK_CTF events [94435530-94435530]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 17:50:02 ERROR Error fetching CTF events [94435640-94435641]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:09 ERROR Error fetching NEG_RISK_CTF events [94435645-94435645]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:22 ERROR Error fetching CTF events [94435653-94435654]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:28 ERROR Error fetching CTF events [94435657-94435658]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:28 ERROR Error fetching NEG_RISK_CTF events [94435657-94435658]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:41 ERROR Error fetching CTF events [94435666-94435666]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:50:41 ERROR Error fetching NEG_RISK_CTF events [94435666-94435666]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 17:57:13 ERROR Error fetching CTF events [94435907-94435908]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 18:04:23 ERROR Error fetching CTF events [94436214-94436215]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:06:27 ERROR Error fetching CTF events [94436297-94436298]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:10:22 ERROR Error fetching CTF events [94436453-94436454]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:10:22 ERROR Error fetching NEG_RISK_CTF events [94436453-94436454]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:16:05 ERROR Error fetching CTF events [94436682-94436683]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:16:05 ERROR Error fetching NEG_RISK_CTF events [94436682-94436683]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:36:02 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 18:36:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 18:36:18 ERROR Error fetching CTF events [94437491-94437492]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:36:19 ERROR Error fetching NEG_RISK_CTF events [94437491-94437492]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:41:06 ERROR Error fetching CTF events [94437682-94437683]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:41:06 ERROR Error fetching NEG_RISK_CTF events [94437682-94437683]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:45:51 ERROR Error fetching CTF events [94437853-94437853]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 18:46:06 ERROR Error fetching CTF events [94437882-94437883]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 18:49:56 ERROR Error fetching NEG_RISK_CTF events [94438016-94438017]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 18:59:36 ERROR Error fetching CTF events [94438423-94438423]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:01:40 ERROR Error fetching NEG_RISK_CTF events [94438505-94438506]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:07:08 ERROR Error fetching CTF events [94438724-94438725]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:16:08 ERROR Error fetching CTF events [94439084-94439085]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:16:08 ERROR Error fetching NEG_RISK_CTF events [94439084-94439085]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:21:05 ERROR Error fetching CTF events [94439282-94439283]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:33:33 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 19:35:32 ERROR Error fetching CTF events [94439840-94439840]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 19:35:34 ERROR Onchain poll error: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 19:35:45 ERROR Error fetching CTF events [94439869-94439869]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 19:35:47 ERROR Error fetching CTF events [94439870-94439871]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 19:36:13 ERROR Error fetching CTF events [94439887-94439888]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 19:36:36 ERROR Error fetching CTF events [94439903-94439903]: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 19:38:50 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 19:41:40 ERROR Error fetching CTF events [94440090-94440106]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:55:35 ERROR Error fetching CTF events [94440662-94440663]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:56:07 ERROR Error fetching CTF events [94440682-94440684]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:56:09 ERROR Error fetching NEG_RISK_CTF events [94440685-94440685]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 19:58:17 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 19:58:30 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 20:00:27 ERROR Error fetching CTF events [94440857-94440857]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:03:32 ERROR Error fetching CTF events [94440980-94440981]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:04:46 ERROR Error fetching CTF events [94441029-94441030]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:06:15 ERROR Error fetching CTF events [94441089-94441089]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:06:37 ERROR Error fetching CTF events [94441103-94441104]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:06:37 ERROR Error fetching NEG_RISK_CTF events [94441103-94441104]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:22:16 ERROR Error fetching CTF events [94441729-94441730]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:22:16 ERROR Error fetching NEG_RISK_CTF events [94441729-94441730]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:48:34 ERROR Error fetching CTF events [94442781-94442782]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 20:51:45 ERROR Error fetching NEG_RISK_CTF events [94442908-94442909]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:01:07 ERROR Error fetching CTF events [94443283-94443284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:06:05 ERROR Error fetching CTF events [94443482-94443483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:06:05 ERROR Error fetching NEG_RISK_CTF events [94443482-94443483]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:11:07 ERROR Error fetching CTF events [94443683-94443684]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:16:14 ERROR Error fetching CTF events [94443888-94443889]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:16:14 ERROR Error fetching NEG_RISK_CTF events [94443888-94443889]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:21:05 ERROR Error fetching CTF events [94444082-94444083]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:36:05 ERROR Error fetching NEG_RISK_CTF events [94444682-94444683]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:41:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 21:42:50 ERROR Error fetching CTF events [94444952-94444953]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 21:43:44 ERROR Onchain poll error: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-25 22:04:29 ERROR Error fetching CTF events [94445818-94445819]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:04:29 ERROR Error fetching NEG_RISK_CTF events [94445818-94445819]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:11:04 ERROR Error fetching CTF events [94446081-94446082]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:11:04 ERROR Error fetching NEG_RISK_CTF events [94446081-94446082]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:18:44 ERROR Error fetching CTF events [94446388-94446389]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:19:29 ERROR Error fetching CTF events [94446418-94446419]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 22:35:23 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-25 22:35:24 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-25 22:35:24 ERROR Network error fetching 0x722a...d6ed: 
2026-09-25 22:35:24 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-25 22:35:24 ERROR Network error fetching 0x0011...4333: 
2026-09-25 22:40:56 ERROR Network error fetching 0xf916...e770: Server disconnected without sending a response.
2026-09-25 22:50:04 ERROR Error fetching CTF events [94447639-94447642]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:13:05 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-25 23:18:19 ERROR Error fetching CTF events [94448771-94448772]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:18:50 ERROR Error fetching CTF events [94448792-94448793]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:19:16 ERROR Error fetching NEG_RISK_CTF events [94448809-94448810]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:20:31 ERROR Error fetching NEG_RISK_CTF events [94448859-94448860]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:25:32 ERROR Error fetching CTF events [94449060-94449061]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:25:51 ERROR Error fetching NEG_RISK_CTF events [94449073-94449074]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:26:19 ERROR Error fetching NEG_RISK_CTF events [94449091-94449092]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:29:20 ERROR Error fetching NEG_RISK_CTF events [94449212-94449213]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:36:23 ERROR Error fetching CTF events [94449494-94449495]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:40:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 23:47:23 ERROR Error fetching NEG_RISK_CTF events [94449934-94449935]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:49:09 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-25 23:49:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-25 23:55:10 ERROR Error fetching CTF events [94450245-94450246]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:57:00 ERROR Error fetching CTF events [94450319-94450320]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:57:00 ERROR Error fetching NEG_RISK_CTF events [94450319-94450320]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:00:14 ERROR Error fetching CTF events [94450448-94450449]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:00:14 ERROR Error fetching NEG_RISK_CTF events [94450448-94450449]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:02:22 ERROR Error fetching NEG_RISK_CTF events [94450533-94450534]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:05:54 ERROR Error fetching CTF events [94450675-94450675]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:06:49 ERROR Error fetching CTF events [94450711-94450712]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:16:40 ERROR Error fetching CTF events [94451105-94451106]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:28:05 ERROR Error fetching CTF events [94451562-94451563]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:28:05 ERROR Error fetching NEG_RISK_CTF events [94451562-94451563]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:28:16 ERROR Error fetching NEG_RISK_CTF events [94451569-94451570]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:33:57 ERROR Error fetching CTF events [94451796-94451797]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:36:17 ERROR Error fetching CTF events [94451890-94451891]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:37:50 ERROR Error fetching CTF events [94451952-94451953]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:37:50 ERROR Error fetching NEG_RISK_CTF events [94451952-94451953]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:41:39 ERROR Error fetching CTF events [94452104-94452105]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:41:39 ERROR Error fetching NEG_RISK_CTF events [94452104-94452105]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:44:22 ERROR Error fetching NEG_RISK_CTF events [94452213-94452214]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:49:08 ERROR Error fetching CTF events [94452404-94452405]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:53:00 ERROR Error fetching CTF events [94452559-94452560]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 00:54:48 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 00:54:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 00:55:48 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 01:00:51 ERROR Error fetching CTF events [94452873-94452873]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:00:51 ERROR Error fetching NEG_RISK_CTF events [94452873-94452873]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:04:14 ERROR Error fetching NEG_RISK_CTF events [94453008-94453008]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:04:37 ERROR Error fetching CTF events [94453024-94453024]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:07:50 ERROR Error fetching CTF events [94453152-94453153]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:08:11 ERROR Error fetching CTF events [94453166-94453167]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:10:16 ERROR Error fetching CTF events [94453249-94453250]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:14:35 ERROR Error fetching CTF events [94453422-94453423]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:14:35 ERROR Error fetching NEG_RISK_CTF events [94453422-94453423]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:15:28 ERROR Error fetching NEG_RISK_CTF events [94453457-94453458]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:24:04 ERROR Error fetching NEG_RISK_CTF events [94453801-94453802]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:24:06 ERROR Error fetching CTF events [94453803-94453803]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:25:25 ERROR Error fetching NEG_RISK_CTF events [94453855-94453856]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:25:50 ERROR Error fetching NEG_RISK_CTF events [94453872-94453873]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:27:44 ERROR Error fetching CTF events [94453948-94453949]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:28:36 ERROR Error fetching NEG_RISK_CTF events [94453982-94453983]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:28:52 ERROR Error fetching CTF events [94453994-94453994]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:28:52 ERROR Error fetching NEG_RISK_CTF events [94453994-94453994]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:30:47 ERROR Error fetching CTF events [94454070-94454071]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:31:43 ERROR Error fetching CTF events [94454107-94454108]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:31:43 ERROR Error fetching NEG_RISK_CTF events [94454107-94454108]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 02:26:10 TRADE [LIVE] BUY $6.40 on '' @ 0.8500, order 0x5540f913e6...
2026-09-25 02:26:14 TRADE [verify] FILLED: BUY 7.53 shares on '' @ 0.8500
2026-09-25 08:27:59 ERROR Error fetching CTF events [94413158-94413159]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:16:24 ERROR Error fetching NEG_RISK_CTF events [94417468-94417474]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 12:57:54 INFO  [recovery] No pending orders to recover
2026-09-25 13:24:06 INFO  [recovery] No pending orders to recover
2026-09-25 13:38:50 INFO  [recovery] No pending orders to recover
2026-09-25 14:52:53 TRADE [LIVE] BUY $6.40 on '' @ 0.6300, order 0x557fb8a720...
2026-09-25 14:52:54 TRADE [verify] FILLED: BUY 10.16 shares on '' @ 0.6300
2026-09-25 16:30:57 ERROR Error fetching NEG_RISK_CTF events [94432477-94432478]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:18:18 ERROR Error fetching CTF events [94448771-94448772]: {'code': -32000, 'message': 'invalid block range params'}
