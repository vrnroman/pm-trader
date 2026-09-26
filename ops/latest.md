# ops digest 2026-09-26T17:09:39.238356+00:00 (last 24h)

## money state
{"cash": 114.302403, "open_cost": 10.9, "equity": 125.2, "floor": 30.0, "stated": 80.0, "spend": {"date": "2026-09-26", "spent_usd": 19.2, "cap_usd": null, "remaining_usd": null, "daily_loss_stop_usd": 45.0, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 68, "tier": {"1a": 0, "1b": 19.2, "1c": 0}, "ts": 1790442511.1608975, "day": "2026-09-26"}

## arm: {"armed": true, "ts": 1790414614.1373932, "by": "owner:claude-session", "reason": "owner instruction 2026-09-26 via Claude session: do actual deals under the new limits (1 a day for new wallets, 20 for the others, 45 USD daily-loss stop)", "first_armed_ts": 1788617432.0499406, "floor_override": false, "daily_loss_override_day": null}
## spend today: {"date": "2026-09-26", "spent_usd": 19.2, "wallet_copies": {"0xd25156e222c9b907b128e27c36821fdb41db4d37": 1, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": 1, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": 1}, "wallet_copies_yesterday": {"0x722abb5460060870d46728bf45f66a6b1635d6ed": 1, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": 1}, "yesterday": "2026-09-25", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790402937.394338, "n_acts": 4000, "n_resolved_markets": 646, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 380, "roi": 0.0146, "trimmed": -0.0135, "ok": false}, "200": {"n": 430, "roi": 0.0297, "trimmed": 0.0034, "ok": false}, "150": {"n": 446, "roi": 0.037, "trimmed": 0.0102, "ok": false}, "100": {"n": 481, "roi": 0.0445, "trimmed": 0.0198, "ok": false}}, "chosen": null}, "floor_usd": null}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790402951.5675707, "n_acts": 4000, "n_resolved_markets": 1144, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 437, "roi": 0.0376, "trimmed": 0.0147, "ok": false}, "200": {"n": 504, "roi": 0.0448, "trimmed": 0.0246, "ok": false}, "150": {"n": 546, "roi": 0.0412, "trimmed": 0.0225, "ok": false}, "100": {"n": 622, "roi": 0.0392, "trimmed": 0.0228, "ok": false}}, "chosen": null}, "floor_usd": null}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790402964.3429935, "n_acts": 4000, "n_resolved_markets": 1415, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 47, "roi": 0.0214, "trimmed": -0.069, "ok": false}, "200": {"n": 77, "roi": 0.0166, "trimmed": -0.0646, "ok": false}, "150": {"n": 104, "roi": 0.0244, "trimmed": -0.0456, "ok": false}, "100": {"n": 159, "roi": 0.039, "trimmed": -0.0107, "ok": false}}, "chosen": null}, "floor_usd": null}, "0x722abb5460060870d46728bf45f66a6b1635d6ed": {"wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed", "tier": "1b", "ts": 1789491938.939273, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403012.1562374, "n_acts": 4000, "n_resolved_markets": 946, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 163, "roi": 0.09, "trimmed": 0.0548, "ok": false}, "200": {"n": 178, "roi": 0.0519, "trimmed": 0.0191, "ok": false}, "150": {"n": 204, "roi": 0.0252, "trimmed": -0.0038, "ok": false}, "100": {"n": 246, "roi": 0.0515, "trimmed": 0.0226, "ok": false}}, "chosen": null}, "floor_usd": null}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"wallet": "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333", "tier": "1b", "ts": 1789752841.6491823, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403034.1411688, "n_acts": 4000, "n_resolved_markets": 1673, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 296, "roi": 0.2121, "trimmed": 0.1773, "ok": true}, "200": {"n": 373, "roi": 0.2017, "trimmed": 0.1682, "ok": true}, "150": {"n": 428, "roi": 0.2023, "trimmed": 0.1731, "ok": true}, "100": {"n": 511, "roi": 0.1979, "trimmed": 0.1693, "ok": true}}, "chosen": 300.0}, "floor_usd": 300.0}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"wallet": "0xf49614e63fb15383d4a9b717a1be03ad2410fe79", "tier": "1b", "ts": 1789827877.6900246, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403074.6571865, "n_acts": 4000, "n_resolved_markets": 173, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 179, "roi": 0.0772, "trimmed": 0.0067, "ok": false}, "200": {"n": 214, "roi": 0.0199, "trimmed": -0.0409, "ok": false}, "150": {"n": 224, "roi": 0.0251, "trimmed": -0.0329, "ok": false}, "100": {"n": 229, "roi": 0.0273, "trimmed": -0.0293, "ok": false}}, "chosen": null}, "floor_usd": null}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"wallet": "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770", "tier": "1b", "ts": 1789992497.9469755, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403083.8554258, "n_acts": 1065, "n_resolved_markets": 174, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 100, "roi": 0.116, "trimmed": 0.0063, "ok": true}, "200": {"n": 100, "roi": 0.116, "trimmed": 0.0063, "ok": true}, "150": {"n": 100, "roi": 0.1132, "trimmed": 0.0034, "ok": true}, "100": {"n": 100, "roi": 0.1132, "trimmed": 0.0034, "ok": true}}, "chosen": 300.0}, "floor_usd": 300.0}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"wallet": "0xd25156e222c9b907b128e27c36821fdb41db4d37", "tier": "1b", "ts": 1790166550.4519851, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403093.1450658, "n_acts": 4000, "n_resolved_markets": 232, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 43, "roi": 0.2283, "trimmed": 0.0469, "ok": true}, "200": {"n": 69, "roi": 0.1561, "trimmed": 0.0428, "ok": true}, "150": {"n": 93, "roi": 0.1034, "trimmed": 0.0186, "ok": true}, "100": {"n": 111, "roi": 0.1021, "trimmed": 0.0079, "ok": true}}, "chosen": 300.0}, "floor_usd": 300.0}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43", "tier": "1b", "ts": 1790266340.2195778, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790403109.883757, "n_acts": 2191, "n_resolved_markets": 306, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 118, "roi": 0.2493, "trimmed": 0.1965, "ok": true}, "200": {"n": 164, "roi": 0.2549, "trimmed": 0.2121, "ok": true}, "150": {"n": 182, "roi": 0.2872, "trimmed": 0.2351, "ok": true}, "100": {"n": 209, "roi": 0.219, "trimmed": 0.1727, "ok": true}}, "chosen": 150.0}, "floor_usd": 150.0}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "tier": "1b", "ts": 1790408391.9935262, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790408379.9945147, "n_acts": 4000, "n_resolved_markets": 1090, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 189, "roi": 0.3047, "trimmed": 0.255, "ok": true}, "200": {"n": 252, "roi": 0.4401, "trimmed": 0.3501, "ok": true}, "150": {"n": 288, "roi": 0.4479, "trimmed": 0.3461, "ok": true}, "100": {"n": 328, "roi": 0.4889, "trimmed": 0.4001, "ok": true}}, "chosen": 100.0}, "floor_usd": 100.0}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "tier": "1b", "ts": 1790408419.3071265, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790408379.9945147, "n_acts": 4000, "n_resolved_markets": 1115, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 184, "roi": 0.3379, "trimmed": 0.2774, "ok": true}, "200": {"n": 248, "roi": 0.3215, "trimmed": 0.2644, "ok": true}, "150": {"n": 274, "roi": 0.3628, "trimmed": 0.3003, "ok": true}, "100": {"n": 334, "roi": 0.3917, "trimmed": 0.3408, "ok": true}}, "chosen": 100.0}, "floor_usd": 100.0}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "tier": "1b", "ts": 1790408446.4940124, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790408379.9945147, "n_acts": 4000, "n_resolved_markets": 111, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 70, "roi": 0.1968, "trimmed": 0.0823, "ok": true}, "200": {"n": 82, "roi": 0.2277, "trimmed": 0.1194, "ok": true}, "150": {"n": 91, "roi": 0.1844, "trimmed": 0.0858, "ok": true}, "100": {"n": 102, "roi": 0.1718, "trimmed": 0.0745, "ok": true}}, "chosen": 200.0}, "floor_usd": 200.0}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "tier": "1b", "ts": 1790419382.3355591, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790419321.1807199, "n_acts": 4000, "n_resolved_markets": 1805, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 299, "roi": -0.0176, "trimmed": -0.0473, "ok": false}, "200": {"n": 353, "roi": -0.0056, "trimmed": -0.0518, "ok": false}, "150": {"n": 388, "roi": 0.018, "trimmed": -0.0266, "ok": false}, "100": {"n": 419, "roi": 0.0416, "trimmed": -0.0053, "ok": false}}, "chosen": null}, "floor_usd": null}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da", "tier": "1b", "ts": 1790419516.3906574, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790419321.1807199, "n_acts": 4000, "n_resolved_markets": 227, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 64, "roi": 0.3523, "trimmed": 0.1587, "ok": true}, "200": {"n": 80, "roi": 0.3118, "trimmed": 0.148, "ok": true}, "150": {"n": 91, "roi": 0.2654, "trimmed": 0.1145, "ok": true}, "100": {"n": 105, "roi": 0.2965, "trimmed": 0.1446, "ok": true}}, "chosen": 300.0}, "floor_usd": 300.0}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c", "tier": "1b", "ts": 1790419544.395236, "source": "telegram-gate", "floor_row": {"label": "backward replay (copy-and-hold at their price, first entry, clean era)", "ts": 1790419321.1807199, "n_acts": 4000, "n_resolved_markets": 686, "era": 1784976482.215206, "bars": {"min_n": 15, "min_roi": 0.1, "trimmed_min": 0.0}, "at": {"300": {"n": 161, "roi": -0.0379, "trimmed": -0.0666, "ok": false}, "200": {"n": 264, "roi": 0.0001, "trimmed": -0.023, "ok": false}, "150": {"n": 330, "roi": -0.013, "trimmed": -0.0315, "ok": false}, "100": {"n": 408, "roi": -0.0307, "trimmed": -0.0466, "ok": false}}, "chosen": null}, "floor_usd": null}}
## tier exposure: {"1a": [0, 0], "1b": [19.2, 3], "1c": [0, 0]}
## probation: {"0x722abb5460060870d46728bf45f66a6b1635d6ed": {"since": 1789491935.7564917, "settled": 0, "held_said": true}, "0x00110b8ef00db2a1a6bbe1198e52fc4eb5a84333": {"since": 1789752828.6614223, "settled": 0}, "0xf49614e63fb15383d4a9b717a1be03ad2410fe79": {"since": 1789827868.9550335, "settled": 0}, "0xf91683432c57581b0c8c58eb3bd0d6e5f03fe770": {"since": 1789992496.5955625, "settled": 0}, "0xd25156e222c9b907b128e27c36821fdb41db4d37": {"since": 1790166548.6465027, "settled": 0}, "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43": {"since": 1790266317.6788435, "settled": 0}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"since": 1790408379.9945147, "settled": 0}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"since": 1790408379.9945147, "settled": 0}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"since": 1790408379.9945147, "settled": 0}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"since": 1790419321.1807199, "settled": 0}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"since": 1790419321.1807199, "settled": 0}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"since": 1790419321.1807199, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
benched  0x00110b8e: 204 settled, 85% won vs 69% needed, net +16.3% on $192,432, worst day -2,112, 21 of 42 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x09b045ba: 25 settled, 68% won vs 57% needed, net +8.4% on $9,621, worst day -333, 24 of 24 exits under 10 min
benched  0x1985327e: 42 settled, 69% won vs 55% needed, net +17.4% on $15,818, worst day -535, 41 of 41 exits under 10 min
benched  0x3f3aa700: 213 settled, 50% won vs 54% needed, net +4.6% on $651,690, worst day -24,321, 1 of 5 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
benched  0x4980930d: 8 settled, 62% won vs 50% needed, net +83.6% on $13,057, worst day -1,358, 0 of 4 exits under 10 min
in form  0x5213eb85: 88 settled, 47% won vs 38% needed, net +7.6% on $43,944, worst day -2,314, 2 of 6 exits under 10 min
in form  0x722abb54: 79 settled, 78% won vs 74% needed, net +8.8% on $137,763, worst day -2,522, 6 of 65 exits under 10 min
benched  0x73653992: 6 settled, 83% won vs 72% needed, net +82.6% on $4,089, worst day -330, 0 of 4 exits under 10 min
benched  0x984ffef1: 34 settled, 68% won vs 53% needed, net +46.9% on $26,041, worst day -1,257, 4 of 10 exits under 10 min
benched  0x9f15613e: 318 settled, 52% won vs 47% needed, net +5.2% on $994,487, worst day -31,964, 12 of 17 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xd25156e2: 67 settled, 67% won vs 47% needed, net +36.0% on $37,343, worst day -2,469, 3 of 26 exits under 10 min (capped: 10.0 of 14 days read, 5500 rows)
benched  0xeef6ad0e: no settled bets on our slice in 14 days
benched  0xf49614e6: 61 settled, 51% won vs 51% needed, net -2.3% on $191,182, worst day -11,771, 4 of 8 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
in form  0xf9168343: 53 settled, 55% won vs 48% needed, net +2.8% on $146,637, worst day -6,320, 2 of 33 exits under 10 min
benched  0xfd3e6449: 68 settled, 65% won vs 71% needed, net -4.1% on $50,698, worst day -2,632, 19 of 22 exits under 10 min (capped: window read in full, older lookback cut, 5500 rows)
two clocks: 102 matched fills over 1.0 d, api lag p50 14.2s, chain lag p50 4.3s, chain earlier by 6.7s at the median; api-only 226, chain-only 904, replayed rows 0; CHAIN IS PRIMARY
⏱ api lag cost, last 7d (estimate): +9.82 USD over 3780 fills at $6.40 each, +0.000 USD a fill at the median, chain earlier by 13.5s

## watcher (28 wakes in 24h)
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
{"ts": 1790400443.427056, "kind": "held", "woke_because": "6fbcddbc9dfb", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
{"ts": 1790400803.4656682, "kind": "escalate", "woke_because": "dcba498fc237", "concluded": "The chain RPC is rejecting CTF and NEG_RISK_CTF event reads with -32000 invalid block range params, so the bot's primary on-chain trade feed is fully down. This is the same fault the SRE already escalated and disarmed for one hour ago, but the owner re-armed via telegram 0.3h ago with no reason while the e
{"ts": 1790401280.8729014, "kind": "note", "woke_because": "6fbcddbc9dfb", "concluded": "The Polygon RPC is returning -32000 invalid block range params on live CTF and NEG_RISK_CTF head polls, so the primary chain read path is down while the deploy at d5be6a3 is unchanged, which points to an RPC or node sync fault and not a code bug. I already disarmed for this 1.1h ago, the owner deliberately re-
{"ts": 1790401624.9833918, "kind": "held", "woke_because": "dcba498fc237", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
{"ts": 1790401865.099971, "kind": "disarm", "woke_because": "dcba498fc237", "concluded": "The chain event reader is fully down because the RPC returns -32000 invalid block range params for CTF and NEG_RISK_CTF block polls, and chain is the primary fill reconciliation path (chain-only 656 vs api-only 8, CHAIN IS PRIMARY). The bot is armed and can still take copy signals from the API path, but it ca
{"ts": 1790402257.5439508, "kind": "held", "woke_because": "dcba498fc237", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
{"ts": 1790402497.5712512, "kind": "analyst", "woke_because": "daily check of min150-r1", "concluded": "+10.6 pp vs control on 138 settled copies, day 1 of 14", "did": "exp min150-r1 live: +10.6 pp vs control on 138 settled copies, day 1 of 14", "cost_usd": 0.0}
{"ts": 1790402497.5712512, "kind": "analyst", "woke_because": "void of min150", "concluded": "harness_pp -7.49 on 65 copies is within one standard error (recomputed se 7.9 pp; per-copy sd ~90 pp gives a chance band near +-31 pp), while the 48 matched copies both books took agreed to the cent (recomputed mismatch 0 of 30). The 1.5 pp whole-book tolerance that voided it (legacy why, not the harness_
{"ts": 1790402791.4233766, "kind": "analyst", "woke_because": "supervise", "concluded": "started min150-r1 (pid 7, first start since this supervisor came up)", "did": "started min150-r1 (pid 7, first start since this supervisor came up)", "cost_usd": 0.0}
{"ts": 1790403272.3858454, "kind": "note", "woke_because": "dcba498fc237", "concluded": "An external RPC node is returning -32000 invalid block range params on CTF and NEG_RISK_CTF event reads, which is the primary chain path for fill reconciliation. The bot is already disarmed to paper by a prior ai-sre action, so the 6 recurrences since the disarm place no real orders and cannot mis-confirm fill
{"ts": 1790404291.371484, "kind": "held", "woke_because": "51c53b9cd7c8", "concluded": "1 wake(s) held: 4 already this hour", "did": "nothing (rate)", "cost_usd": 0.0}
{"ts": 1790407524.410194, "kind": "note", "woke_because": "907b728a6b72", "concluded": "The inventory API sync failed with an empty error string, which is the same Polymarket API and RPC outage that is already throwing 404 price errors, CTF invalid-block-range errors and the earlier 'API sync failed: Server disconnected' line (13ad3e5ddfe8). The bot is already disarmed by ai-sre for that outage, s
{"ts": 1790408430.9750392, "kind": "note", "woke_because": "b36205e25762", "concluded": "The new fingerprint is a routine INFO set Z auto-admission, not a fault, and the bot is already back to paper for the separate chain reconciliation incident the owner was told about. The notable detail is the paper versus real gap: 0x09b045ba was admitted on trimmed paper edge +28% (paper ROI +36.9%) while its
{"ts": 1790408782.3187575, "kind": "nothing", "woke_because": "e5755fdaf81b", "concluded": "The line is an INFO confirming the bot delivered its own escalation about the known chain RPC getLogs failure (RPC -32000 invalid block range) to the owner. It is the escalation path working as designed, not a new fault. The underlying chain read outage is already handled: the bot disarmed itself back to pa
{"ts": 1790414620.1020496, "kind": "note", "woke_because": "d9f102ca20ef, 590e8b8a4374", "concluded": "The owner deliberately armed real money via a Claude session at 09:23:34, seconds after the 09:20:39 deploy of the new-limits build 07f0b74 and the 09:22:01 restart. The two waking fingerprints (d9f102ca20ef and 590e8b8a4374) are the same arm event; the first line at 09:23:05 lacked the daily-los
{"ts": 1790415658.8132656, "kind": "note", "woke_because": "59f5d5ebf4a6", "concluded": "The daily-cap line changed from a numeric spend cap to 'no spend cap (the day stops after $45 lost)' because the owner re-armed at 09:23 today with new limits that set cap_usd to null, which created this new fingerprint. This is faithful to the owner's own arm instruction (1/day new wallets, 20/day others, $45
{"ts": 1790419671.6146815, "kind": "nothing", "woke_because": "7d62a20b0696", "concluded": "Cause: the form tracker benched wallet 0xeef6ad0e because it has no settled bets on our slice in 14 days, which is the safe direction and removes it from ranking. This is not a fault: an inactive wallet produces no fills, so real money cannot follow it even though set Z lists it as copyable once armed. The 
## live limits (owner's number, and the analyst's where one is in force)
LIVE_MAX_PER_WALLET_DAY: 20 (owner) band 1..20
FETCH_INTERVAL: 3.0 (owner) band 2..5
OPS_REARM_CLEAR_S: 900.0 (owner) band 600.0..1800.0
OPS_REARM_MAX_PER_DAY: 3 (owner) band 1..3
FORM_DAYS: 14.0 (owner) band 7.0..21.0
## book B at each slice floor (raw numbers; the gate reads the one marked)
b300 (floor $300): 7485 settled, 278 open, realized +2.2%, at their price +3.1% (net -7.7%), win rate 57%, feeds the Z gate
b150 (floor $150): 293 settled, 62 open, realized -5.0%, at their price -4.0% (net -14.9%), win rate 53%
b100 (floor $100): 347 settled, 62 open, realized +2.9%, at their price +3.9% (net -6.9%), win rate 51%
## near the Z door (34 wallets within 2 fails; 1 pass and wait)
0x09b045ba: 1 fail(s): not a scalper at our latency (scalper: 100% of exits within 10 min; uncopyable at our latency)
0x10658d37: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (26 clean (of 26 all-time))
0x141a5834: 1 fail(s): promotion floor still holds (copy ROI +8% < floor +10%)
0x19585131: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (21 clean (of 21 all-time))
0x1985327e: 1 fail(s): not a scalper at our latency (scalper: 100% of exits within 10 min; uncopyable at our latency)
0x3968f7c9: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (18 clean (of 18 all-time))
0x57b25849: 1 fail(s): promotion floor still holds (copy ROI +7% < floor +10%; 2nd-half ROI -10% < -10% (edge decaying))
0x8342720d: 1 fail(s): still positive with its best 3 copies deleted (-0% over 45 copies with its best 3 deleted)
0x91c7d990: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (17 clean (of 17 all-time))
0x984ffef1: 1 fail(s): not a scalper at our latency (scalper: 40% of exits within 10 min; uncopyable at our latency)
0x9f15613e: 1 fail(s): not a scalper at our latency (scalper: 71% of exits within 10 min; uncopyable at our latency)
0xa42f3648: 1 fail(s): ≥30 settled copies IN THE CLEAN ERA (20 clean (of 20 all-time))
## experiments (the analyst's cards; one live at a time)
min150-r1        void   slice floor 300 to 150                             n 138 +10.6 pp  (min150-r1 <- min150, study 2026-09-24-min_usd-cdc749c5)
min150           void   slice floor 300 to 150                             n 128 -1.9 pp  (min150 <- study 2026-09-24-min_usd-cdc749c5)
{"day": "2026-09-26", "id": "min150-r1", "event": "void", "why": "withdrawn: the owner runs this experiment himself in another terminal (Desk note 2026-09-26, s-wo3xsp); not retryable"}
study 2026-09-24-first_entry-152981e2: wallets in 18 -> 18 (stay 18, enter 0, leave 0); copies 3276 -> 3276; ROI at their price +3.5% -> +3.5%
study 2026-09-24-min_usd-cdc749c5: wallets in 19 -> 20 (stay 15, enter 5, leave 4); copies 3567 -> 5216; ROI at their price +2.6% -> +3.7%
study 2026-09-25-wallet_cap-178163d7: wallets in 32 -> 34 (stay 32, enter 2, leave 0); copies 3840 -> 2956; ROI at their price +9.0% -> +11.8%
## questions the study menu could not compute (last 7 days)
2026-09-24 after study 2026-09-24-first_entry-152981e2: With first_entry_only=false as the baseline (copying every buy), how many copies collapse to one per market when we switch it on, and does the +3.5% ROI hold? (missing: This run set both the from and to arms to first_entry_only=true, so there is no every-buy baseline in the frozen table to difference against.)
2026-09-25 after study 2026-09-25-wallet_cap-178163d7: What do the copies in wallet-day slots 4 and 5 actually earn, the ones the live cap of 3 turns away but a cap of 5 would admit? (missing: This run baselined at cap 25 rather than the live 3, so its rows cannot isolate the marginal ROI of the slot 4 and 5 copies; that needs a study framed from {cap:3} to {cap:5}.)
## fingerprints (30 shown)
54ac26fb3ff1 x140 last 0.0h ago [open: 140 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/price body={'S':'S'}
c6d91d798e54 x19 last 0.1h ago [open: 19 hits, no action yet] :: INFO [tiered-risk] tier Nb: released $N of exposure from resolved or closed positions | open now: $N
9d498e122ffb x12 last 0.8h ago [open: 12 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: N settled, N won vs N needed, net N on $N, worst day N, N of N exits under N min
907b728a6b72 x5 last 2.3h ago [open: 5 hits, no action yet] :: ERROR [inventory] API sync failed:
6c813168939b x64 last 2.4h ago [open: 64 hits, no action yet] :: ERROR [py_clob_client_v2] request error: Server disconnected
6eca45f47973 x14 last 2.9h ago [open: 14 hits, no action yet] :: ERROR Network error fetching <hex>: Server disconnected without sending a response.
7a8d58f20915 x12 last 2.9h ago [open: 12 hits, no action yet] :: ERROR Network error fetching <hex>:
51c53b9cd7c8 x4 last 3.0h ago [open: 4 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/book body={'S':'S'}
6f12d4998994 x27 last 3.2h ago [open: 27 hits, no action yet] :: INFO [recovery] No pending orders to recover
6b829965c182 x27 last 3.2h ago [open: 27 hits, no action yet] :: INFO Bot started. Monitoring trades...
9d8a6d2794ec x21 last 3.2h ago [open: 21 hits, no action yet] :: ERROR [py_clob_client_v2] request error status=N url=https://clob.polymarket.com/auth/api-key body={'S':'S'}
c47d62e70341 x27 last 3.2h ago [open: 27 hits, no action yet] :: INFO Received signal N, shutting down...
41cab7e764a5 x16 last 3.4h ago [open: 16 hits, no action yet] :: ERROR [py_clob_client_v2] request error: The read operation timed out
eb7da12386c6 x22 last 4.4h ago [open: 22 hits, no action yet] :: TRADE [LIVE] BUY $N on 'S' @ N, order <hex>...
a77088f7944a x22 last 4.4h ago [open: 22 hits, no action yet] :: INFO [tiered-risk] Recorded tier Nb placement: $N | open: $N / $N
d7140f640d29 x21 last 4.4h ago [open: 21 hits, no action yet] :: TRADE [verify] FILLED: BUY N shares on 'S' @ N
59f5d5ebf4a6 x3 last 4.4h ago [open: 3 hits, no action yet] :: INFO [daily-cap] +$N (copy:Nb) reserved | total today $N / no spend cap (the day stops after $N lost)
b36205e25762 x6 last 6.4h ago [open: 6 hits, no action yet] :: INFO [ops] auto_admit: 'S' -> 'S' | N settled paper copies, paper ROI N, trimmed N, ideal N, real quotes N over N matche
7d62a20b0696 x1 last 6.4h ago [open: 1 hits, no action yet] :: INFO [ops] form: 'S' -> 'S' | <hex>: no settled bets on our slice in N days
c3db66a087f7 x9 last 6.4h ago [open: 9 hits, no action yet] :: WARNING [zset] ADMITTED <hex> to set Z (N over N copies with its best N deleted). Real money may now follow it once arme
13ad3e5ddfe8 x2 last 7.6h ago [open: 2 hits, no action yet] :: ERROR [inventory] API sync failed: Server disconnected without sending a response.
d9f102ca20ef x1 last 7.8h ago [open: 1 hits, no action yet] :: WARNING [live] ARMED for real orders by owner:claude-session: owner instruction NNN via Claude session: do actual deals 
590e8b8a4374 x1 last 7.8h ago [open: 1 hits, no action yet] :: WARNING [live] ARMED for real orders by owner:claude-session: owner instruction NNN via Claude session: do actual deals 
84e240524773 x11 last 8.1h ago [open: 11 hits, no action yet] :: TRADE [DISARMED] would BUY $N on 'S' @ N (from <hex>); the arm is off
dcba498fc237 x188 last 8.5h ago [recurred: 8 hit(s) since the disarm 11.3 h ago] :: ERROR Error fetching CTF events [NN]: {'S': N, 'S': 'S'}
6fbcddbc9dfb x175 last 8.6h ago [recurred: 11 hit(s) since the disarm 12.6 h ago] :: ERROR Error fetching NEG_RISK_CTF events [NN]: {'S': N, 'S': 'S'}
34253fa6334e x6 last 9.1h ago [open: 6 hits, no action yet] :: INFO [AB-RACE] rehearsal line sent, real-money line sent
e5755fdaf81b x1 last 9.4h ago [open: 1 hits, no action yet] :: INFO [ops] escalation_delivered: 'S' -> 'S' | Chain RPC is still failing. CTF and NEG_RISK_CTF getLogs have hit invalid 
4a9f22de1928 x1 last 11.9h ago [open: 1 hits, no action yet] :: WARNING [live] ARMED for real orders by telegram: no reason given
1bd07071cf73 x2 last 19.4h ago [open: 2 hits, no action yet] :: ERROR Onchain poll error: ('S', RemoteDisconnected('S'))

## ledger (25 rows)
{"ts": 1790390490.826207, "day": "2026-09-26", "kind": "sre_escalate", "before": "fingerprint 6fbcddbc9dfb", "after": "owner told", "detail": "175 chain read errors this hour: CTF and NEG_RISK_CTF getLogs rejected with invalid block range params, and chain is your primary fill clock so copy signals may", "push": "BOT", "fingerprint": "6fbcddbc9dfb"}
{"ts": 1790397212.3620746, "day": "2026-09-26", "kind": "sre_disarm", "before": "armed", "after": "disarmed", "detail": "Chain CTF and NEG_RISK_CTF event reads are fully down (RPC -32000 invalid block range params) and chain is the primary fill and inventory channel, so an armed b", "push": "DEAL", "fingerprint": "6fbcddbc9dfb"}
{"ts": 1790400803.4656682, "day": "2026-09-26", "kind": "sre_escalate", "before": "fingerprint dcba498fc237", "after": "owner told", "detail": "Still 164 chain read errors since you re-armed 40 min ago: the CTF feed the bot trades on is fully down, so it is live but blind, 0 traded today and 68 position", "push": "BOT", "fingerprint": "dcba498fc237"}
{"ts": 1790401865.099971, "day": "2026-09-26", "kind": "sre_disarm", "before": "armed", "after": "disarmed", "detail": "Chain fill reconciliation is fully down (RPC -32000 invalid block range) while armed, so the bot can still place copy orders it cannot confirm on chain; back to", "push": "DEAL", "fingerprint": "dcba498fc237"}
{"ts": 1790402790.9767268, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790404170.876388, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790405122.9200625, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790408379.9945147, "day": "2026-09-26", "kind": "auto_admit", "before": "0x09b045ba not in Z", "after": "in set Z, on probation", "detail": "49 settled paper copies, paper ROI +36.9%, trimmed +28.0%, ideal +37.9%, real quotes +1.1% over 30 matched", "push": "WALLET", "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "rail": "real quotes", "floor": "copies at $100: 300 yes +30% (n=189, trimmed +26%) · 200 yes +44% (n=252, trimmed +35%) · 150 yes +45% (n=288, trimmed +35%) · 100 YES +49% (n=328, trimmed +40%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790408379.9945147, "day": "2026-09-26", "kind": "auto_admit", "before": "0x1985327e not in Z", "after": "in set Z, on probation", "detail": "36 settled paper copies, paper ROI +54.9%, trimmed +34.3%, ideal +55.9%, real quotes +19.6% over 20 matched", "push": "WALLET", "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "rail": "real quotes", "floor": "copies at $100: 300 yes +34% (n=184, trimmed +28%) · 200 yes +32% (n=248, trimmed +26%) · 150 yes +36% (n=274, trimmed +30%) · 100 YES +39% (n=334, trimmed +34%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790408379.9945147, "day": "2026-09-26", "kind": "auto_admit", "before": "0x4980930d not in Z", "after": "in set Z, on probation", "detail": "34 settled paper copies, paper ROI +36.5%, trimmed +19.9%, ideal +37.5%, real quotes +33.5% over 26 matched", "push": "WALLET", "wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "rail": "real quotes", "floor": "copies at $200: 300 yes +20% (n=70, trimmed +8%) · 200 YES +23% (n=82, trimmed +12%) · 150 yes +18% (n=91, trimmed +9%) · 100 yes +17% (n=102, trimmed +7%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790408373.9709096, "day": "2026-09-26", "kind": "form", "before": "0x09b045ba unknown", "after": "benched", "detail": "0x09b045ba: 31 settled, 71% won vs 58% needed, net +10.2% on $12,220, worst day -333, 30 of 30 exits under 10 min", "push": null, "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6"}
{"ts": 1790408373.9709096, "day": "2026-09-26", "kind": "form", "before": "0x1985327e unknown", "after": "benched", "detail": "0x1985327e: 51 settled, 71% won vs 54% needed, net +16.8% on $19,607, worst day -535, 49 of 49 exits under 10 min", "push": null, "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab"}
{"ts": 1790408373.9709096, "day": "2026-09-26", "kind": "form", "before": "0x4980930d unknown", "after": "benched", "detail": "0x4980930d: 5 settled, 40% won vs 42% needed, net +54.5% on $6,146, worst day -1,358, 0 of 1 exits under 10 min", "push": null, "wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709"}
{"ts": 1790408764.557082, "day": "2026-09-26", "kind": "escalation_delivered", "before": "routine escalation", "after": "sent", "detail": "Chain RPC is still failing. CTF and NEG_RISK_CTF getLogs have hit invalid block range params without a clean stretch sin", "push": "BOT"}
{"ts": 1790412284.7953641, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790414499.8314414, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790419321.1807199, "day": "2026-09-26", "kind": "auto_admit", "before": "0x5213eb85 not in Z", "after": "in set Z, on probation", "detail": "77 settled paper copies, paper ROI +21.0%, trimmed +10.5%, ideal +22.0%, real quotes +16.3% over 77 matched", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "rail": "real quotes", "floor": "no floor clears the bars, global floor stays: 300 no -2% (n=299, trimmed -5%) · 200 no -1% (n=353, trimmed -5%) · 150 no +2% (n=388, trimmed -3%) · 100 no +4% (n=419, trimmed -1%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790419321.1807199, "day": "2026-09-26", "kind": "auto_admit", "before": "0x73653992 not in Z", "after": "in set Z, on probation", "detail": "41 settled paper copies, paper ROI +15.2%, trimmed +9.2%, ideal +16.2%, real quotes +8.8% over 26 matched", "push": "WALLET", "wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da", "rail": "real quotes", "floor": "copies at $300: 300 YES +35% (n=64, trimmed +16%) · 200 yes +31% (n=80, trimmed +15%) · 150 yes +27% (n=91, trimmed +11%) · 100 yes +30% (n=105, trimmed +14%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790419321.1807199, "day": "2026-09-26", "kind": "auto_admit", "before": "0xeef6ad0e not in Z", "after": "in set Z, on probation", "detail": "75 settled paper copies, paper ROI +10.5%, trimmed +2.8%, ideal +18.1%, real quotes +14.2% over 41 matched", "push": "WALLET", "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c", "rail": "real quotes", "floor": "no floor clears the bars, global floor stays: 300 no -4% (n=161, trimmed -7%) · 200 no +0% (n=264, trimmed -2%) · 150 no -1% (n=330, trimmed -3%) · 100 no -3% (n=408, trimmed -5%); backward replay (copy-and-hold at their price, first entry, clean era)"}
{"ts": 1790419320.2807124, "day": "2026-09-26", "kind": "form", "before": "0x5213eb85 unknown", "after": "in form", "detail": "0x5213eb85: 88 settled, 47% won vs 38% needed, net +7.6% on $43,855, worst day -2,314, 2 of 6 exits under 10 min", "push": null, "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1790419320.2807124, "day": "2026-09-26", "kind": "form", "before": "0x73653992 unknown", "after": "benched", "detail": "0x73653992: 6 settled, 83% won vs 72% needed, net +82.6% on $4,089, worst day -330, 0 of 4 exits under 10 min", "push": null, "wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da"}
{"ts": 1790419320.2807124, "day": "2026-09-26", "kind": "form", "before": "0xeef6ad0e unknown", "after": "benched", "detail": "0xeef6ad0e: no settled bets on our slice in 14 days", "push": null, "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c"}
{"ts": 1790430933.542596, "day": "2026-09-26", "kind": "sre_started", "before": "sidecar", "after": "watching", "detail": "tick 120s", "push": null}
{"ts": 1790439647.632302, "day": "2026-09-26", "kind": "form", "before": "0x722abb54 benched", "after": "in form", "detail": "0x722abb54: 79 settled, 78% won vs 74% needed, net +8.8% on $137,763, worst day -2,522, 6 of 65 exits under 10 min", "push": "WALLET", "wallet": "0x722abb5460060870d46728bf45f66a6b1635d6ed"}
{"ts": 1790439647.632302, "day": "2026-09-26", "kind": "form", "before": "0x984ffef1 in form", "after": "benched", "detail": "0x984ffef1: 34 settled, 68% won vs 53% needed, net +46.9% on $26,041, worst day -1,257, 4 of 10 exits under 10 min", "push": "WALLET", "wallet": "0x984ffef12a23e7af5e2cef8e3283e0ab6a6e9a43"}

## important lines (400)
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
2026-09-26 05:24:55 ERROR Error fetching CTF events [94463436-94463436]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:25:23 ERROR Error fetching NEG_RISK_CTF events [94463454-94463455]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:26:04 ERROR Error fetching CTF events [94463481-94463482]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:26:29 ERROR Error fetching CTF events [94463498-94463499]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:26:29 ERROR Error fetching NEG_RISK_CTF events [94463498-94463499]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:26:56 ERROR Error fetching CTF events [94463516-94463517]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:28:52 ERROR Error fetching CTF events [94463593-94463594]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:29:28 ERROR Error fetching NEG_RISK_CTF events [94463617-94463618]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:29:53 ERROR Error fetching NEG_RISK_CTF events [94463634-94463635]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:29:58 ERROR Error fetching NEG_RISK_CTF events [94463637-94463638]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:31:08 ERROR Error fetching NEG_RISK_CTF events [94463684-94463685]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:31:33 ERROR Error fetching CTF events [94463701-94463702]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:31:40 ERROR Error fetching CTF events [94463705-94463706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:31:40 ERROR Error fetching NEG_RISK_CTF events [94463705-94463706]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:33:01 ERROR Error fetching NEG_RISK_CTF events [94463759-94463760]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:33:07 ERROR Error fetching CTF events [94463764-94463764]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:33:37 ERROR Error fetching CTF events [94463783-94463784]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:34:47 ERROR Error fetching CTF events [94463830-94463831]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:40:12 ERROR Error fetching NEG_RISK_CTF events [94464047-94464048]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:40:48 ERROR Error fetching NEG_RISK_CTF events [94464071-94464072]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:40:55 ERROR Error fetching CTF events [94464075-94464076]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:41:05 ERROR Error fetching NEG_RISK_CTF events [94464082-94464083]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:42:57 ERROR Error fetching CTF events [94464157-94464157]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:44:03 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 05:44:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 05:46:10 ERROR Error fetching CTF events [94464285-94464286]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:47:22 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 05:47:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 05:47:33 ERROR Error fetching NEG_RISK_CTF events [94464341-94464342]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:49:31 ERROR Error fetching NEG_RISK_CTF events [94464419-94464420]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:49:39 ERROR Error fetching NEG_RISK_CTF events [94464425-94464426]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:50:48 ERROR Error fetching CTF events [94464471-94464472]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:51:41 ERROR Error fetching NEG_RISK_CTF events [94464506-94464507]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:55:59 ERROR Error fetching CTF events [94464678-94464679]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:57:24 ERROR Error fetching NEG_RISK_CTF events [94464735-94464735]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:58:05 ERROR Error fetching NEG_RISK_CTF events [94464762-94464763]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:58:15 ERROR Error fetching CTF events [94464769-94464770]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:58:18 ERROR Error fetching CTF events [94464771-94464771]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:58:18 ERROR Error fetching NEG_RISK_CTF events [94464771-94464771]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:59:05 ERROR Error fetching NEG_RISK_CTF events [94464802-94464803]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:00:54 ERROR Error fetching NEG_RISK_CTF events [94464875-94464875]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:01:01 ERROR Error fetching NEG_RISK_CTF events [94464879-94464880]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:01:40 ERROR Error fetching CTF events [94464905-94464906]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:01:40 ERROR Error fetching NEG_RISK_CTF events [94464905-94464906]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:02:44 ERROR Error fetching NEG_RISK_CTF events [94464948-94464949]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:04:20 ERROR Error fetching NEG_RISK_CTF events [94465012-94465013]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:05:13 ERROR Error fetching CTF events [94465047-94465048]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:06:00 INFO  Received signal 15, shutting down...
2026-09-26 06:06:26 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 06:06:27 INFO  Bot started. Monitoring trades...
2026-09-26 06:09:10 ERROR Error fetching NEG_RISK_CTF events [94465206-94465206]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:09:13 ERROR Error fetching NEG_RISK_CTF events [94465207-94465208]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:13:01 ERROR Error fetching CTF events [94465350-94465359]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:17:41 ERROR Error fetching NEG_RISK_CTF events [94465544-94465546]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:17:59 ERROR Error fetching NEG_RISK_CTF events [94465555-94465558]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:20:38 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:20:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:20:40 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:25:20 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:26:06 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:26:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:26:10 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:26:11 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:29:07 INFO  Received signal 15, shutting down...
2026-09-26 06:29:08 ERROR Error fetching CTF events [94465999-94466005]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:29:55 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 06:29:55 INFO  Bot started. Monitoring trades...
2026-09-26 06:30:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/book body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:30:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/book body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:31:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/book body={"error":"No orderbook exists for the requested token id"}
2026-09-26 06:31:39 ERROR Error fetching CTF events [94466105-94466105]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:31:39 ERROR Error fetching NEG_RISK_CTF events [94466105-94466105]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 06:45:05 INFO  Received signal 15, shutting down...
2026-09-26 06:45:47 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 06:45:48 INFO  Bot started. Monitoring trades...
2026-09-26 07:07:13 ERROR Error fetching CTF events [94467524-94467528]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:07:13 ERROR Error fetching NEG_RISK_CTF events [94467524-94467528]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:18:16 ERROR Error fetching NEG_RISK_CTF events [94467966-94467969]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:23:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:23:51 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:24:14 ERROR Error fetching CTF events [94468195-94468208]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:24:32 ERROR [inventory] API sync failed: 
2026-09-26 07:30:15 ERROR [inventory] API sync failed: 
2026-09-26 07:37:14 ERROR Error fetching NEG_RISK_CTF events [94468728-94468728]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:37:16 ERROR Error fetching NEG_RISK_CTF events [94468729-94468730]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:37:18 ERROR Error fetching NEG_RISK_CTF events [94468731-94468731]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:39:52 WARNING [zset] ADMITTED 0x09b045baad1fbe115c70785635a261411774a3b6 to set Z (+28% over 46 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 07:39:55 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:39:56 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:40:18 INFO  [ops] auto_admit: '0x09b045ba not in Z' -> 'in set Z, on probation' | 49 settled paper copies, paper ROI +36.9%, trimmed +28.0%, ideal +37.9%, real quotes +1.1% over 30 matched
2026-09-26 07:40:19 WARNING [zset] ADMITTED 0x1985327e5782c62362dbbdf714c423d40d8f51ab to set Z (+34% over 33 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 07:40:23 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:40:24 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:40:25 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 07:40:44 INFO  [ops] auto_admit: '0x1985327e not in Z' -> 'in set Z, on probation' | 36 settled paper copies, paper ROI +54.9%, trimmed +34.3%, ideal +55.9%, real quotes +19.6% over 20 matched
2026-09-26 07:40:46 WARNING [zset] ADMITTED 0x4980930da4ad1194d4f0fd5e29f17b70a42e5709 to set Z (+20% over 31 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 07:40:48 INFO  [ops] auto_admit: '0x4980930d not in Z' -> 'in set Z, on probation' | 34 settled paper copies, paper ROI +36.5%, trimmed +19.9%, ideal +37.5%, real quotes +33.5% over 26 matched
2026-09-26 07:40:52 INFO  [ops] form: '0x09b045ba unknown' -> 'benched' | 0x09b045ba: 31 settled, 71% won vs 58% needed, net +10.2% on $12,220, worst day -333, 30 of 30 exits under 10 min
2026-09-26 07:40:56 INFO  [ops] form: '0x1985327e unknown' -> 'benched' | 0x1985327e: 51 settled, 71% won vs 54% needed, net +16.8% on $19,607, worst day -535, 49 of 49 exits under 10 min
2026-09-26 07:41:00 INFO  [ops] form: '0x4980930d unknown' -> 'benched' | 0x4980930d: 5 settled, 40% won vs 42% needed, net +54.5% on $6,146, worst day -1,358, 0 of 1 exits under 10 min
2026-09-26 07:46:05 INFO  [ops] escalation_delivered: 'routine escalation' -> 'sent' | Chain RPC is still failing. CTF and NEG_RISK_CTF getLogs have hit invalid block range params without a clean stretch sin
2026-09-26 07:57:07 ERROR Error fetching CTF events [94469524-94469524]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:57:07 ERROR Error fetching NEG_RISK_CTF events [94469524-94469524]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 07:57:12 ERROR Error fetching NEG_RISK_CTF events [94469527-94469527]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:00:11 INFO  [AB-RACE] rehearsal line sent, real-money line sent
2026-09-26 08:00:35 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 08:01:08 ERROR Error fetching NEG_RISK_CTF events [94469684-94469685]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:08:13 ERROR Error fetching CTF events [94469967-94469968]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:08:13 ERROR Error fetching NEG_RISK_CTF events [94469967-94469968]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:08:15 ERROR Error fetching CTF events [94469969-94469969]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:08:15 ERROR Error fetching NEG_RISK_CTF events [94469969-94469969]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:21:07 ERROR Error fetching CTF events [94470482-94470484]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:21:37 ERROR Error fetching NEG_RISK_CTF events [94470503-94470504]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:29:12 ERROR Error fetching CTF events [94470806-94470807]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:31:38 ERROR Error fetching CTF events [94470904-94470905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:31:38 ERROR Error fetching NEG_RISK_CTF events [94470904-94470905]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:34:13 ERROR Error fetching CTF events [94471008-94471008]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:34:15 ERROR Error fetching NEG_RISK_CTF events [94471009-94471009]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:35:14 ERROR Error fetching CTF events [94471048-94471048]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 08:39:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 08:39:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 08:44:32 INFO  Received signal 15, shutting down...
2026-09-26 08:45:09 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 08:45:10 INFO  Bot started. Monitoring trades...
2026-09-26 09:06:49 ERROR [inventory] API sync failed: 
2026-09-26 09:15:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 09:21:21 INFO  Received signal 15, shutting down...
2026-09-26 09:21:29 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 09:22:00 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 09:22:01 INFO  Bot started. Monitoring trades...
2026-09-26 09:23:05 WARNING [live] ARMED for real orders by owner:claude-session: owner instruction 2026-09-26 via Claude session: do actual deals under the new limits (1/day new wallets, 20 others,  daily-loss stop)
2026-09-26 09:23:34 WARNING [live] ARMED for real orders by owner:claude-session: owner instruction 2026-09-26 via Claude session: do actual deals under the new limits (1 a day for new wallets, 20 for the others, 45 USD daily-loss stop)
2026-09-26 09:27:23 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $6.40
2026-09-26 09:33:04 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-26 09:39:10 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $6.40 / no spend cap (the day stops after $45 lost)
2026-09-26 09:39:15 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $12.80 / $200.00
2026-09-26 09:49:58 ERROR Network error fetching 0xf496...fe79: 
2026-09-26 09:49:58 ERROR Network error fetching 0xf916...e770: 
2026-09-26 09:49:58 ERROR Network error fetching 0xd251...4d37: 
2026-09-26 09:49:58 ERROR Network error fetching 0x984f...9a43: 
2026-09-26 09:49:58 ERROR Network error fetching 0x09b0...a3b6: Server disconnected without sending a response.
2026-09-26 10:43:02 WARNING [zset] ADMITTED 0x5213eb85fcd465c8927a8382f95dd2dc22306a35 to set Z (+11% over 74 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 10:43:10 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 10:43:12 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 10:44:57 INFO  [ops] auto_admit: '0x5213eb85 not in Z' -> 'in set Z, on probation' | 77 settled paper copies, paper ROI +21.0%, trimmed +10.5%, ideal +22.0%, real quotes +16.3% over 77 matched
2026-09-26 10:45:16 WARNING [zset] ADMITTED 0x736539924a5602b37a03a54fc12c1cc8f98964da to set Z (+9% over 38 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 10:45:42 INFO  [ops] auto_admit: '0x73653992 not in Z' -> 'in set Z, on probation' | 41 settled paper copies, paper ROI +15.2%, trimmed +9.2%, ideal +16.2%, real quotes +8.8% over 26 matched
2026-09-26 10:45:44 WARNING [zset] ADMITTED 0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c to set Z (+3% over 43 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-26 10:46:45 INFO  [ops] auto_admit: '0xeef6ad0e not in Z' -> 'in set Z, on probation' | 75 settled paper copies, paper ROI +10.5%, trimmed +2.8%, ideal +18.1%, real quotes +14.2% over 41 matched
2026-09-26 10:46:54 INFO  [ops] form: '0x5213eb85 unknown' -> 'in form' | 0x5213eb85: 88 settled, 47% won vs 38% needed, net +7.6% on $43,855, worst day -2,314, 2 of 6 exits under 10 min
2026-09-26 10:47:00 INFO  [ops] form: '0x73653992 unknown' -> 'benched' | 0x73653992: 6 settled, 83% won vs 72% needed, net +82.6% on $4,089, worst day -330, 0 of 4 exits under 10 min
2026-09-26 10:47:08 INFO  [ops] form: '0xeef6ad0e unknown' -> 'benched' | 0xeef6ad0e: no settled bets on our slice in 14 days
2026-09-26 11:17:23 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 11:54:20 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 12:08:44 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 12:08:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 12:22:11 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $12.80 / no spend cap (the day stops after $45 lost)
2026-09-26 12:22:12 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $19.20 / $200.00
2026-09-26 12:31:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 12:31:32 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 12:42:22 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 12:42:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 12:45:20 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $19.20 / no spend cap (the day stops after $45 lost)
2026-09-26 12:45:21 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $25.60 / $200.00
2026-09-26 12:52:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 12:55:19 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 12:55:24 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 13:03:15 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 13:30:21 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 13:30:26 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 13:43:35 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 13:43:40 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-26 13:55:20 INFO  Received signal 15, shutting down...
2026-09-26 13:55:47 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-26 13:55:48 INFO  Bot started. Monitoring trades...
2026-09-26 14:08:16 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:09:04 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/book body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:09:12 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:10:26 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:13:47 ERROR Network error fetching 0x0011...4333: 
2026-09-26 14:13:47 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-26 14:13:49 ERROR Network error fetching 0x3f3a...e8fd: Server disconnected without sending a response.
2026-09-26 14:13:49 ERROR Network error fetching 0x722a...d6ed: Server disconnected without sending a response.
2026-09-26 14:16:16 ERROR Network error fetching 0xf496...fe79: Server disconnected without sending a response.
2026-09-26 14:16:16 ERROR Network error fetching 0x984f...9a43: Server disconnected without sending a response.
2026-09-26 14:16:16 ERROR Network error fetching 0xf916...e770: Server disconnected without sending a response.
2026-09-26 14:17:45 ERROR [inventory] API sync failed: 
2026-09-26 14:39:38 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:44:50 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:44:51 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:44:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-26 14:44:58 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 14:50:14 ERROR [inventory] API sync failed: 
2026-09-26 14:54:52 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 16:21:48 INFO  [ops] form: '0x722abb54 benched' -> 'in form' | 0x722abb54: 79 settled, 78% won vs 74% needed, net +8.8% on $137,763, worst day -2,522, 6 of 65 exits under 10 min
2026-09-26 16:21:59 INFO  [ops] form: '0x984ffef1 in form' -> 'benched' | 0x984ffef1: 34 settled, 68% won vs 53% needed, net +46.9% on $26,041, worst day -1,257, 4 of 10 exits under 10 min
2026-09-26 16:30:18 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 17:03:29 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $19.20
2026-09-26 17:03:42 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-26 17:08:47 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-25 23:18:18 ERROR Error fetching CTF events [94448771-94448772]: {'code': -32000, 'message': 'invalid block range params'}
2026-09-26 05:00:13 TRADE [DISARMED] would BUY $6.40 on '' @ 0.8276 (from 0xfd3e...5a7a); the arm is off
2026-09-26 06:06:27 INFO  [recovery] No pending orders to recover
2026-09-26 06:11:25 TRADE [DISARMED] would BUY $6.40 on '' @ 0.5300 (from 0x3f3a...e8fd); the arm is off
2026-09-26 06:22:03 TRADE [DISARMED] would BUY $6.40 on '' @ 0.3700 (from 0x9f15...bdb3); the arm is off
2026-09-26 06:29:10 TRADE [DISARMED] would BUY $6.40 on '' @ 0.4400 (from 0x3f3a...e8fd); the arm is off
2026-09-26 06:29:55 INFO  [recovery] No pending orders to recover
2026-09-26 06:30:43 TRADE [DISARMED] would BUY $6.40 on 'North Macedonia vs. Switzerland: O/U 2.5' @ 0.4400 (from 0x3f3a...e8fd); the arm is off
2026-09-26 06:42:58 TRADE [DISARMED] would BUY $6.40 on '' @ 0.5800 (from 0x3f3a...e8fd); the arm is off
2026-09-26 06:45:48 INFO  [recovery] No pending orders to recover
2026-09-26 06:56:56 TRADE [DISARMED] would BUY $6.40 on '' @ 0.5800 (from 0x3f3a...e8fd); the arm is off
2026-09-26 07:08:56 TRADE [DISARMED] would BUY $6.40 on '' @ 0.6300 (from 0x3f3a...e8fd); the arm is off
2026-09-26 07:23:43 TRADE [DISARMED] would BUY $6.40 on '' @ 0.5000 (from 0x3f3a...e8fd); the arm is off
2026-09-26 07:23:54 TRADE [DISARMED] would BUY $6.40 on '' @ 0.5000 (from 0x3f3a...e8fd); the arm is off
2026-09-26 08:45:10 INFO  [recovery] No pending orders to recover
2026-09-26 08:59:54 TRADE [DISARMED] would BUY $6.40 on '' @ 0.2800 (from 0x3f3a...e8fd); the arm is off
2026-09-26 09:22:01 INFO  [recovery] No pending orders to recover
2026-09-26 09:39:11 TRADE [LIVE] BUY $6.40 on '' @ 0.9000, order 0xc7613e77e1...
2026-09-26 09:39:17 TRADE [verify] FILLED: BUY 5.00 shares on '' @ 0.9000
2026-09-26 12:22:11 TRADE [LIVE] BUY $6.40 on 'Map Handicap: HERO (-1.5) vs Sangal (+1.' @ 0.5100, order 0xdee08e5f50...
2026-09-26 12:22:12 TRADE [verify] FILLED: BUY 12.55 shares on 'Map Handicap: HERO (-1.5) vs Sangal (+1.' @ 0.5100
2026-09-26 12:45:21 TRADE [LIVE] BUY $6.40 on '' @ 0.5700, order 0x99c8fab930...
2026-09-26 12:45:22 TRADE [verify] FILLED: BUY 11.23 shares on '' @ 0.5700
2026-09-26 13:55:48 INFO  [recovery] No pending orders to recover
