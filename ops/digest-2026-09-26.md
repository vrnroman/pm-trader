# ops digest 2026-09-26T05:21:00.579100+00:00 (last 24h)

## money state
{"cash": 112.890933, "open_cost": 6.4, "equity": 119.29, "floor": 30.0, "stated": 80.0, "spend": {"date": "2026-09-26", "spent_usd": 0.0, "cap_usd": 54.0, "remaining_usd": 54.0, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 68, "tier": {"1a": 0, "1b": 12.8, "1c": 0}, "ts": 1790399779.7867594, "day": "2026-09-26"}

## arm: {"armed": true, "ts": 1790399544.217656, "by": "telegram", "reason": "", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-26", "spent_usd": 0.0, "wallet_copies": {}, "wallet_copies_yesterday": {"0x722abb5460060870d46728bf45f66a6b1635d6ed": 1, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": 1}, "yesterday": "2026-09-25", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x722abb5460060870d46728bf45f66a6b1635d6ed": {"wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed", "tier": "1b", "ts": 1789491938.939273, "source": "telegram-gate"}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"wallet": "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333", "tier": "1b", "ts": 1789752841.6491823, "source": "telegram-gate"}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"wallet": "0xf49614e63fb15383d4a9b717a1be03ad2410fe79", "tier": "1b", "ts": 1789827877.6900246, "source": "telegram-gate"}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"wallet": "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770", "tier": "1b", "ts": 1789992497.9469755, "source": "telegram-gate"}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"wallet": "0xd25156e222c9b907b128e27c36821fdb41db4d37", "tier": "1b", "ts": 1790166550.4519851, "source": "telegram-gate"}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43", "tier": "1b", "ts": 1790266340.2195778, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [12.8, 2], "1c": [0, 0]}
## probation: {"0x722abb5460060870d46728bf45f66a6b1635d6ed": {"since": 1789491935.7564917, "settled": 0, "held_said": true}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"since": 1789752828.6614223, "settled": 0}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"since": 1789827868.9550335, "settled": 0}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"since": 1789992496.5955625, "settled": 0}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"since": 1790166548.6465027, "settled": 0}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"since": 1790266317.6788435, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
benched  0x00110b8e: 215 settled, 85% won vs 69% needed, net +16.9% on $199,178, worst day -2,112, 22 of 43 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x3f3aa700: 231 settled, 51% won vs 54% needed, net +5.6% on $690,648, worst day -24,321, 1 of 6 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x722abb54: 84 settled, 77% won vs 75% needed, net +3.9% on $152,696, worst day -3,391, 7 of 68 exits under 10 min
in form  0x984ffef1: 32 settled, 72% won vs 53% needed, net +56.3% on $23,930, worst day -87, 3 of 8 exits under 10 min
benched  0x9f15613e: 342 settled, 52% won vs 48% needed, net +6.3% on $1,090,193, worst day -31,088, 13 of 18 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xd25156e2: 68 settled, 65% won vs 48% needed, net +28.9% on $38,469, worst day -2,191, 3 of 27 exits under 10 min (capped: 9.8 of 14 days read, 5500 rows)
benched  0xf49614e6: 68 settled, 51% won vs 51% needed, net +11.1% on $233,297, worst day -11,771, 4 of 10 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xf9168343: 53 settled, 55% won vs 48% needed, net +2.8% on $146,637, worst day -6,320, 2 of 33 exits under 10 min
benched  0xfd3e6449: 68 settled, 63% won vs 70% needed, net -4.8% on $49,836, worst day -2,632, 19 of 22 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
two clocks: 71 matched fills over 1.0 d, api lag p50 16.2s, chain lag p50 2.8s, chain earlier by 11.3s at the median; api-only 8, chain-only 637, replayed rows 0; CHAIN IS PRIMARY
⏱ api lag cost, last 7d (estimate): +17.29 USD over 3218 fills at $6.40 each, +0.000 USD a fill at the median, chain earlier by 13.6s

## watcher (30 wakes in 24h)
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
{"ts": 1790388940.3839388, "kind": "note", "woke_because": "dcba498fc237", "concluded": "The Polygon RPC provider is rejecting chain event queries at or just ahead of its synced head with -32000 invalid block range params. The block cursor keeps advancing (94455795 to 94455799 to 94455822) so the poller is not stuck and the ranges are well formed, meaning these are transient near-head or provider 
{"ts": 1790390490.826207, "kind": "escalate", "woke_because": "6fbcddbc9dfb", "concluded": "The Polygon RPC is deterministically rejecting the CTF and NEG_RISK_CTF getLogs reads with code -32000 invalid block range params over current 2-block ranges, which points to the node being behind the bot's block cursor or a provider change rather than a network blip. This is the chain event poller, and the
{"ts": 1790390726.1046498, "kind": "nothing", "woke_because": "6fbcddbc9dfb", "concluded": "The RPC node is returning -32000 invalid block range params for CTF and NEG_RISK_CTF event fetches on recent and single-block ranges (94457021-94457021), which is the load balanced node lagging behind the chain head and rejecting queries for blocks it has not synced yet. This is a transient upstream read fa
{"ts": 1790397033.480417, "kind": "nothing", "woke_because": "dcba498fc237", "concluded": "The cause is an upstream RPC returning -32000 invalid block range params on small CTF event range reads, which happens when the node lags behind the requested head block. This is the same chain read storm the box already escalated to the owner about 1.7h ago, whose detail explicitly named CTF and NEG_RISK_CT
{"ts": 1790397212.3620746, "kind": "disarm", "woke_because": "6fbcddbc9dfb", "concluded": "Polymarket's chain RPC is rejecting every CTF and NEG_RISK_CTF event query with -32000 invalid block range params, so on-chain event ingestion is fully down. Block numbers in the log advance normally with wall time, so this is not the poller racing the chain head; every poll fails, sustained at about 264 per
{"ts": 1790398184.407604, "kind": "note", "woke_because": "6fbcddbc9dfb", "concluded": "Upstream RPC is returning -32000 invalid block range params on chain CTF and NEG_RISK_CTF event reads, and chain is the primary fill and inventory channel. The requested ranges are single or adjacent blocks (94462024-94462024, 94462019-94462020), which are valid, so this is a provider side fault and not our ran
{"ts": 1790398855.3686247, "kind": "nothing", "woke_because": "84e240524773", "concluded": "The disarm placed 0.5h ago is working: a live copy signal from 0xfd3e6449 arrived and the bot logged a would-BUY instead of placing real money because the arm is off. This DISARMED line is the paper path refusing the trade, which is exactly the intended behaviour during the chain read outage that triggered 
{"ts": 1790399603.2158184, "kind": "held", "woke_because": "4a9f22de1928", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
{"ts": 1790399723.400475, "kind": "held", "woke_because": "6fbcddbc9dfb", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
## live limits (owner's number, and the analyst's where one is in force)
LIVE_MAX_PER_WALLET_DAY: 3 (owner) band 1..3
FETCH_INTERVAL: 3.0 (owner) band 2..5
OPS_REARM_CLEAR_S: 900.0 (owner) band 600.0..1800.0
OPS_REARM_MAX_PER_DAY: 3 (owner) band 1..3
FORM_DAYS: 14.0 (owner) band 7.0..21.0
## book B at each slice floor (raw numbers; the gate reads the one marked)
b300 (floor $300): 7427 settled, 246 open, realized +2.1%, at their price +3.1% (net -7.7%), win rate 57%, feeds the Z gate
b150 (floor $150): 231 settled, 40 open, realized -8.6%, at their price -7.6% (net -18.5%), win rate 52%
b100 (floor $100): 310 settled, 55 open, realized +5.5%, at their price +6.5% (net -4.3%), win rate 51%
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
0x9f15613e: 1 fail(s): not a scalper at our latency (scalper: 72% of exits within 10 min; uncopyable at our latency)
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
6fbcddbc9dfb x133 last 0.1h ago [recurred: 16 hit(s) since the disarm 0.8 h ago] :: ERROR Error fetching NEG_RISK_CTF events [NN]: {'S': N, 'S': 'S'}
4a9f22de1928 x1 last 0.1h ago [open: 1 hits, no action yet] :: WARNING [live] ARMED for real orders by telegram: no reason given
dcba498fc237 x156 last 0.2h ago [open: 156 hits, no action yet] :: ERROR Error fetching CTF events [NN]: {'S': N, 'S': 'S'}
84e240524773 x1 last 0.3h ago [open: 1 hits, no action yet] :: TRADE [DISARMED] would BUY $N on 'S' @ N (from <hex>); the arm is off
54ac26fb3ff1 x81 last 1.2h ago [open: 81 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/price body={'S':'S'}
6c813168939b x46 last 2.9h ago [open: 46 hits, no action yet] :: ERROR [py_clob_client_v2] request error: Server disconnected
41cab7e764a5 x8 last 2.9h ago [open: 8 hits, no action yet] :: ERROR [py_clob_client_v2] request error: The read operation timed out
13ad3e5ddfe8 x1 last 6.1h ago [open: 1 hits, no action yet] :: ERROR [inventory] API sync failed: Server disconnected without sending a response.
6eca45f47973 x8 last 6.7h ago [open: 8 hits, no action yet] :: ERROR Network error fetching <hex>: Server disconnected without sending a response.
7a8d58f20915 x6 last 6.7h ago [open: 6 hits, no action yet] :: ERROR Network error fetching <hex>:
1bd07071cf73 x2 last 7.6h ago [open: 2 hits, no action yet] :: ERROR Onchain poll error: ('S', RemoteDisconnected('S'))
ca12f2f09597 x6 last 9.7h ago [open: 6 hits, no action yet] :: ERROR Error fetching CTF events [NN]: ('S', RemoteDisconnected('S'))
c6d91d798e54 x17 last 12.2h ago [open: 17 hits, no action yet] :: INFO [tiered-risk] tier Nb: released $N of exposure from resolved or closed positions | open now: $N
001dacd732e7 x1 last 12.2h ago [open: 1 hits, no action yet] :: INFO [ops] probation_held: 'S' -> 'S' | untested is not failed; the clock keeps running
9d498e122ffb x5 last 13.2h ago [open: 5 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N, N of N exits under N min
69fd3dc7d27e x21 last 14.4h ago [open: 21 hits, no action yet] :: INFO [daily-cap] +$N (copy:Nb) reserved | total today $N / $N
eb7da12386c6 x19 last 14.4h ago [open: 19 hits, no action yet] :: TRADE [LIVE] BUY $N on 'S' @ N, order <hex>...
a77088f7944a x19 last 14.4h ago [open: 19 hits, no action yet] :: INFO [tiered-risk] Recorded tier Nb placement: $N | open: $N / $N
d7140f640d29 x18 last 14.4h ago [open: 18 hits, no action yet] :: TRADE [verify] FILLED: BUY N shares on 'S' @ N
6f12d4998994 x21 last 15.7h ago [open: 21 hits, no action yet] :: INFO [recovery] No pending orders to recover
6b829965c182 x21 last 15.7h ago [open: 21 hits, no action yet] :: INFO Bot started. Monitoring trades...
9d8a6d2794ec x15 last 15.7h ago [open: 15 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/auth/api-key body={'S':'S'}
c47d62e70341 x21 last 15.7h ago [open: 21 hits, no action yet] :: INFO Received signal N, shutting down...
5f7bb5f89b09 x2 last 16.3h ago [open: 2 hits, no action yet] :: INFO [daily-cap] $N reservation kept: the post's fate is ambiguous (no order id)
1d84f68e4a14 x1 last 16.3h ago [open: 1 hits, no action yet] :: ERROR [exec] Order placement failed: PolyApiException[status_code=None, error_message=Request exception!]
705df184a49d x1 last 16.3h ago [open: 1 hits, no action yet] :: ERROR [exec] Order placement returned None for 'S': exchange error: Request exception!
962fd1d59e01 x1 last 16.3h ago [open: 1 hits, no action yet] :: INFO [ops] escalation_delivered: 'S' -> 'S' | Loss streak is N losing copies in a row, up from N a week ago. The bot's o
34253fa6334e x5 last 21.3h ago [open: 5 hits, no action yet] :: INFO [AB-RACE] rehearsal line sent, real-money line sent
2497cd50ff7d x3 last 25.7h ago [open: 3 hits, no action yet] :: INFO [ops] settled: 'S' -> 'S' | lost N on 'S' (<hex>, tier Nb)
c3db66a087f7 x3 last 37.1h ago [open: 3 hits, no action yet] :: WARNING [zset] ADMITTED <hex> to set Z (N over N copies with its best N deleted). Real money may now follow it once arme

## ledger (9 rows)
{"ts": 1790316060.064088, "day": "2026-09-25", "kind": "analyst_study", "before": "2026-09-25-wallet_cap-178163d7", "after": "wallets in 32 -> 34 (stay 32, enter 2, leave 0); copies 3840 -> 2956; ROI at their price +9.0% -> +11.8%", "detail": "estimate: 40 of 183 wallets studied (most settled first); over book B's own settled rows at their price; in = positive at their price on at least 10 settled cop", "push": "BOT"}
{"ts": 1790341080.423772, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790341088.5600715, "day": "2026-09-25", "kind": "escalation_delivered", "before": "routine escalation", "after": "sent", "detail": "Loss streak is 7 losing copies in a row, up from 4 a week ago. The bot's only alert fired once, at 4, on Sep 18 (bankrol", "push": "BOT"}
{"ts": 1790342643.4500165, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790343524.3963003, "day": "2026-09-25", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790352581.6513798, "day": "2026-09-25", "kind": "form", "before": "0x722abb54 in form", "after": "benched", "detail": "0x722abb54: 86 settled, 78% won vs 75% needed, net +6.1% on $164,749, worst day -3,391, 7 of 70 exits under 10 min", "push": "WALLET", "wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed"}
{"ts": 1790355972.0362878, "day": "2026-09-25", "kind": "probation_held", "before": "0x722abb54 on probation (10 days on probation)", "after": "held: 0 live copy(ies) settled, under the 2 the bar needs", "detail": "untested is not failed; the clock keeps running", "push": null, "wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed"}
{"ts": 1790390490.826207, "day": "2026-09-26", "kind": "sre_escalate", "before": "fingerprint 6fbcddbc9dfb", "after": "owner told", "detail": "175 chain read errors this hour: CTF and NEG_RISK_CTF getLogs rejected with invalid block range params, and chain is your primary fill clock so copy signals may", "push": "BOT", "fingerprint": "6fbcddbc9dfb"}
{"ts": 1790397212.3620746, "day": "2026-09-26", "kind": "sre_disarm", "before": "armed", "after": "disarmed", "detail": "Chain CTF and NEG_RISK_CTF event reads are fully down (RPC -32000 invalid block range params) and chain is the primary fill and inventory channel, so an armed b", "push": "DEAL", "fingerprint": "6fbcddbc9dfb"}

## important lines (400)
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
2026-09-26 01:38:09 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 01:41:11 ERROR Error fetching NEG_RISK_CTF events [94454486-94454487]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:41:58 ERROR Error fetching NEG_RISK_CTF events [94454517-94454518]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:42:35 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 01:42:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 01:43:29 ERROR Error fetching CTF events [94454578-94454579]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:48:34 ERROR Error fetching NEG_RISK_CTF events [94454782-94454782]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:51:32 ERROR Error fetching CTF events [94454900-94454901]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:51:38 ERROR Error fetching CTF events [94454904-94454905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:51:38 ERROR Error fetching NEG_RISK_CTF events [94454904-94454905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:56:04 ERROR Error fetching CTF events [94455081-94455082]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:56:04 ERROR Error fetching NEG_RISK_CTF events [94455081-94455082]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:57:46 ERROR Error fetching NEG_RISK_CTF events [94455149-94455150]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 01:59:43 ERROR Error fetching CTF events [94455227-94455228]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:02:16 ERROR Error fetching CTF events [94455329-94455330]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:02:16 ERROR Error fetching NEG_RISK_CTF events [94455329-94455330]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:02:58 ERROR Error fetching NEG_RISK_CTF events [94455357-94455358]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:04:50 ERROR Error fetching CTF events [94455432-94455433]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:05:09 ERROR Error fetching CTF events [94455445-94455446]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:05:10 ERROR Error fetching NEG_RISK_CTF events [94455445-94455446]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:05:37 ERROR Error fetching CTF events [94455463-94455464]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:08:31 ERROR Error fetching CTF events [94455579-94455580]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:10:31 ERROR Error fetching CTF events [94455659-94455660]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:12:15 ERROR Error fetching CTF events [94455729-94455729]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:12:15 ERROR Error fetching NEG_RISK_CTF events [94455729-94455729]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:12:51 ERROR Error fetching NEG_RISK_CTF events [94455753-94455753]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:12:53 ERROR Error fetching CTF events [94455754-94455755]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:13:57 ERROR Error fetching CTF events [94455795-94455798]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:14:00 ERROR Error fetching CTF events [94455799-94455799]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:14:36 ERROR Error fetching NEG_RISK_CTF events [94455822-94455823]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:19:58 ERROR Error fetching NEG_RISK_CTF events [94456038-94456038]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:22:31 ERROR Error fetching CTF events [94456139-94456140]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:22:39 ERROR Error fetching CTF events [94456145-94456146]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:25:34 ERROR Error fetching CTF events [94456261-94456262]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:26:05 ERROR Error fetching CTF events [94456282-94456283]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:26:57 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 02:27:02 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 02:29:10 ERROR Error fetching NEG_RISK_CTF events [94456405-94456405]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:32:09 ERROR Error fetching CTF events [94456525-94456525]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:33:37 ERROR Error fetching NEG_RISK_CTF events [94456583-94456584]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:34:43 ERROR Error fetching NEG_RISK_CTF events [94456628-94456628]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:37:32 ERROR Error fetching CTF events [94456740-94456741]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:37:34 ERROR Error fetching NEG_RISK_CTF events [94456742-94456742]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:37:47 ERROR Error fetching CTF events [94456750-94456751]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:38:25 ERROR Error fetching NEG_RISK_CTF events [94456776-94456776]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:39:34 ERROR Error fetching NEG_RISK_CTF events [94456821-94456822]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:40:59 ERROR Error fetching CTF events [94456878-94456879]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:41:05 ERROR Error fetching CTF events [94456882-94456883]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:41:05 ERROR Error fetching NEG_RISK_CTF events [94456882-94456883]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:42:13 ERROR Error fetching CTF events [94456927-94456928]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:43:49 ERROR Error fetching CTF events [94456991-94456992]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:44:33 ERROR Error fetching NEG_RISK_CTF events [94457021-94457021]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:44:57 ERROR Error fetching NEG_RISK_CTF events [94457037-94457037]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:45:26 ERROR Error fetching CTF events [94457056-94457057]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:46:17 ERROR Error fetching NEG_RISK_CTF events [94457090-94457091]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:46:41 ERROR Error fetching NEG_RISK_CTF events [94457106-94457107]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:46:43 ERROR Error fetching CTF events [94457108-94457108]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:46:48 ERROR Error fetching NEG_RISK_CTF events [94457111-94457111]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:47:16 ERROR Error fetching NEG_RISK_CTF events [94457129-94457130]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:47:33 ERROR Error fetching NEG_RISK_CTF events [94457141-94457141]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:47:52 ERROR Error fetching CTF events [94457153-94457154]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:47:52 ERROR Error fetching NEG_RISK_CTF events [94457153-94457154]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:50:23 ERROR Error fetching CTF events [94457254-94457255]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:50:23 ERROR Error fetching NEG_RISK_CTF events [94457254-94457255]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:50:27 ERROR Error fetching CTF events [94457257-94457258]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:50:27 ERROR Error fetching NEG_RISK_CTF events [94457257-94457258]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:51:38 ERROR Error fetching CTF events [94457304-94457305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:51:38 ERROR Error fetching NEG_RISK_CTF events [94457304-94457305]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:52:04 ERROR Error fetching CTF events [94457321-94457322]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:52:23 ERROR Error fetching NEG_RISK_CTF events [94457334-94457335]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:53:32 ERROR Error fetching NEG_RISK_CTF events [94457360-94457360]: {'code': -32002, 'message': 'request timed out'}
2026-09-26 02:54:56 ERROR Error fetching NEG_RISK_CTF events [94457436-94457437]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:55:05 ERROR Error fetching NEG_RISK_CTF events [94457442-94457442]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 02:59:22 ERROR Error fetching CTF events [94457613-94457614]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:02:28 ERROR Error fetching CTF events [94457737-94457738]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:05:02 ERROR Error fetching NEG_RISK_CTF events [94457840-94457840]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:06:34 ERROR Error fetching CTF events [94457901-94457902]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:06:34 ERROR Error fetching NEG_RISK_CTF events [94457901-94457902]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:12:25 ERROR Error fetching CTF events [94458136-94458136]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:12:25 ERROR Error fetching NEG_RISK_CTF events [94458136-94458136]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:13:46 ERROR Error fetching CTF events [94458190-94458190]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:13:48 ERROR Error fetching CTF events [94458191-94458191]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:13:48 ERROR Error fetching NEG_RISK_CTF events [94458191-94458191]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:15:14 ERROR Error fetching CTF events [94458248-94458249]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:15:49 ERROR Error fetching CTF events [94458271-94458272]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:17:13 ERROR Error fetching CTF events [94458327-94458328]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:17:37 ERROR Error fetching NEG_RISK_CTF events [94458343-94458344]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:18:37 ERROR Error fetching CTF events [94458383-94458384]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:24:30 ERROR Error fetching CTF events [94458619-94458620]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:24:30 ERROR Error fetching NEG_RISK_CTF events [94458619-94458620]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:24:33 ERROR Error fetching NEG_RISK_CTF events [94458621-94458621]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:27:32 ERROR Error fetching CTF events [94458740-94458741]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:29:58 ERROR Error fetching CTF events [94458837-94458838]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:30:08 ERROR Error fetching NEG_RISK_CTF events [94458844-94458845]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:36:22 ERROR Error fetching NEG_RISK_CTF events [94459093-94459094]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:36:36 ERROR Error fetching NEG_RISK_CTF events [94459103-94459103]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:38:35 ERROR Error fetching CTF events [94459182-94459182]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:38:45 ERROR Error fetching CTF events [94459189-94459189]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:39:28 ERROR Error fetching CTF events [94459217-94459218]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:40:15 ERROR Error fetching NEG_RISK_CTF events [94459249-94459249]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:40:17 ERROR Error fetching NEG_RISK_CTF events [94459250-94459251]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:40:36 ERROR Error fetching NEG_RISK_CTF events [94459263-94459264]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:42:20 ERROR Error fetching CTF events [94459332-94459333]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:42:20 ERROR Error fetching NEG_RISK_CTF events [94459332-94459333]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:42:50 ERROR Error fetching CTF events [94459352-94459353]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:42:50 ERROR Error fetching NEG_RISK_CTF events [94459352-94459353]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:43:43 ERROR Error fetching CTF events [94459387-94459388]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:46:10 ERROR Error fetching CTF events [94459485-94459486]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:47:26 ERROR Error fetching CTF events [94459536-94459537]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:47:30 ERROR Error fetching CTF events [94459539-94459540]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:48:13 ERROR Error fetching NEG_RISK_CTF events [94459568-94459568]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:48:53 ERROR Error fetching CTF events [94459594-94459595]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:48:53 ERROR Error fetching NEG_RISK_CTF events [94459594-94459595]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:48:59 ERROR Error fetching NEG_RISK_CTF events [94459598-94459599]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:49:28 ERROR Error fetching CTF events [94459618-94459618]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:50:53 ERROR Error fetching CTF events [94459674-94459675]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:50:53 ERROR Error fetching NEG_RISK_CTF events [94459674-94459675]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:51:58 ERROR Error fetching NEG_RISK_CTF events [94459717-94459718]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:53:13 ERROR Error fetching CTF events [94459767-94459768]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:54:10 ERROR Error fetching CTF events [94459805-94459806]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:55:25 ERROR Error fetching NEG_RISK_CTF events [94459855-94459856]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:56:50 ERROR Error fetching NEG_RISK_CTF events [94459912-94459913]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 03:58:52 ERROR Error fetching NEG_RISK_CTF events [94459993-94459994]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:01:38 ERROR Error fetching NEG_RISK_CTF events [94460104-94460105]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:07:02 ERROR Error fetching CTF events [94460320-94460321]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:09:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 04:09:19 ERROR Error fetching NEG_RISK_CTF events [94460412-94460412]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:11:35 ERROR Error fetching CTF events [94460502-94460503]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:11:56 ERROR Error fetching CTF events [94460516-94460517]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:15:26 ERROR Error fetching CTF events [94460656-94460657]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:18:43 ERROR Error fetching NEG_RISK_CTF events [94460788-94460788]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:25:12 ERROR Error fetching CTF events [94461047-94461048]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:30:24 ERROR Error fetching CTF events [94461255-94461256]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:07 ERROR Error fetching CTF events [94461283-94461284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:07 ERROR Error fetching NEG_RISK_CTF events [94461283-94461284]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:24 ERROR Error fetching CTF events [94461294-94461295]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:36 ERROR Error fetching NEG_RISK_CTF events [94461303-94461303]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:38 ERROR Error fetching NEG_RISK_CTF events [94461304-94461304]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:31:59 ERROR Error fetching CTF events [94461318-94461319]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:34:05 ERROR Error fetching NEG_RISK_CTF events [94461402-94461403]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:34:07 ERROR Error fetching NEG_RISK_CTF events [94461404-94461404]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:35:47 ERROR Error fetching CTF events [94461470-94461471]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:37:20 ERROR Error fetching NEG_RISK_CTF events [94461532-94461533]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:37:41 ERROR Error fetching NEG_RISK_CTF events [94461546-94461547]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:39:04 ERROR Error fetching NEG_RISK_CTF events [94461601-94461602]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:40:43 ERROR Error fetching CTF events [94461667-94461668]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:47:17 ERROR Error fetching CTF events [94461930-94461931]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:49:31 ERROR Error fetching NEG_RISK_CTF events [94462019-94462020]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:49:37 ERROR Error fetching NEG_RISK_CTF events [94462024-94462024]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:51:33 ERROR Error fetching CTF events [94462101-94462102]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:55:29 ERROR Error fetching NEG_RISK_CTF events [94462258-94462259]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 04:59:20 ERROR Error fetching CTF events [94462412-94462413]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:02:38 ERROR Error fetching NEG_RISK_CTF events [94462544-94462545]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:02:46 ERROR Error fetching CTF events [94462550-94462550]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:03:49 ERROR Error fetching NEG_RISK_CTF events [94462591-94462592]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:05:51 ERROR Error fetching NEG_RISK_CTF events [94462673-94462674]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:08:16 ERROR Error fetching CTF events [94462769-94462770]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:08:16 ERROR Error fetching NEG_RISK_CTF events [94462769-94462770]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:08:33 ERROR Error fetching NEG_RISK_CTF events [94462781-94462781]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:10:16 ERROR Error fetching CTF events [94462850-94462850]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:11:19 ERROR Error fetching CTF events [94462891-94462892]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:12:24 WARNING [live] ARMED for real orders by telegram: no reason given
2026-09-26 05:13:35 ERROR Error fetching NEG_RISK_CTF events [94462982-94462983]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:14:45 ERROR Error fetching NEG_RISK_CTF events [94463029-94463029]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:15:02 ERROR Error fetching NEG_RISK_CTF events [94463040-94463041]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 08:27:59 ERROR Error fetching CTF events [94413158-94413159]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 10:16:24 ERROR Error fetching NEG_RISK_CTF events [94417468-94417474]: {'code': -32002, 'message': 'request timed out'}
2026-09-25 12:57:54 INFO  [recovery] No pending orders to recover
2026-09-25 13:24:06 INFO  [recovery] No pending orders to recover
2026-09-25 13:38:50 INFO  [recovery] No pending orders to recover
2026-09-25 14:52:53 TRADE [LIVE] BUY $6.40 on '' @ 0.6300, order 0x557fb8a720...
2026-09-25 14:52:54 TRADE [verify] FILLED: BUY 10.16 shares on '' @ 0.6300
2026-09-25 16:30:57 ERROR Error fetching NEG_RISK_CTF events [94432477-94432478]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-25 23:18:18 ERROR Error fetching CTF events [94448771-94448772]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:00:13 TRADE [DISARMED] would BUY $6.40 on '' @ 0.8276 (from 0xfd3e...5a7a); the arm is off
