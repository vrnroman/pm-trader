# ops digest 2026-09-14T10:27:27.025937+00:00 (last 24h)

## money state
{"cash": 75.510531, "open_cost": 29.65, "equity": 105.16, "floor": 56.0, "stated": 80.0, "spend": {"date": "2026-09-14", "spent_usd": 0.0, "cap_usd": 32.0, "remaining_usd": 32.0, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 63, "tier": {"1a": 0, "1b": 0, "1c": 0}, "ts": 1789381404.3866663, "day": "2026-09-14"}

## arm: {"armed": true, "ts": 1789312200.3067093, "by": "telegram", "reason": "", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-14", "spent_usd": 0.0, "wallet_copies": {}, "wallet_copies_yesterday": {"0x05878ac343c1387d592042d788424412733ac40b": 1, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": 1}, "yesterday": "2026-09-13", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x05878ac343c1387d592042d788424412733ac40b": {"wallet": "0x05878ac343c1387d592042d788424412733ac40b", "tier": "1b", "ts": 1789234932.162376, "source": "telegram-gate"}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "tier": "1b", "ts": 1789234933.8880239, "source": "telegram-gate"}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "tier": "1b", "ts": 1789235975.528039, "source": "telegram-gate"}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "tier": "1b", "ts": 1789235977.260961, "source": "telegram-gate"}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "tier": "1b", "ts": 1789236561.2672133, "source": "telegram-gate"}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2", "tier": "1b", "ts": 1789236563.7443745, "source": "telegram-gate"}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da", "tier": "1b", "ts": 1789237156.0778086, "source": "telegram-gate"}, "0xd970693a3384dc762b191707a4927ac3814bbbba": {"wallet": "0xd970693a3384dc762b191707a4927ac3814bbbba", "tier": "1b", "ts": 1789237157.586524, "source": "telegram-gate"}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c", "tier": "1b", "ts": 1789317836.75121, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [0, 0], "1c": [0, 0]}
## probation: {"0x05878ac343c1387d592042d788424412733ac40b": {"since": 1789234925.3749237, "settled": 0}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"since": 1789234925.3749237, "settled": 0}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"since": 1789235966.2959275, "settled": 0}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"since": 1789235966.2959275, "settled": 0}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"since": 1789236552.0468774, "settled": 0}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"since": 1789236552.0468774, "settled": 0}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"since": 1789237149.0874667, "settled": 0}, "0xd970693a3384dc762b191707a4927ac3814bbbba": {"since": 1789237149.0874667, "settled": 0}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"since": 1789317835.1951635, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
in form  0x05878ac3: 162 settled, 55% won vs 47% needed, net +32.8% on $147,966, worst day -2,592
in form  0x09b045ba: 51 settled, 76% won vs 61% needed, net +21.5% on $19,500, worst day -200
in form  0x1985327e: 56 settled, 82% won vs 56% needed, net +24.2% on $22,045, worst day -159
benched  0x3f3aa700: 160 settled, 51% won vs 54% needed, net -1.2% on $414,324, worst day -39,107
benched  0x4980930d: 10 settled, 40% won vs 36% needed, net +63.9% on $11,693, worst day -1,364
benched  0x5213eb85: 94 settled, 46% won vs 38% needed, net -9.3% on $51,904, worst day -2,023
benched  0x57b25849: 67 settled, 48% won vs 46% needed, net -5.4% on $70,154, worst day -3,854
benched  0x73653992: 20 settled, 85% won vs 76% needed, net +57.2% on $36,210, worst day +108
benched  0x9f15613e: 203 settled, 51% won vs 50% needed, net +8.4% on $554,669, worst day -19,498
in form  0xd970693a: 60 settled, 75% won vs 56% needed, net +20.7% on $24,889, worst day +52
benched  0xeef6ad0e: no settled bets on our slice in 14 days
benched  0xfd3e6449: 15 settled, 73% won vs 76% needed, net +5.3% on $10,622, worst day -1,129

## ledger (4 rows)
{"ts": 1789311962.0330517, "day": "2026-09-13", "kind": "push:floor_near", "before": null, "after": "⚠️ <b>Bankroll $62.30 is within 20% of the $56 floor.</b> A top-up of about $10 would restore the margin; under the floo", "detail": "", "push": "DEAL"}
{"ts": 1789317835.1951635, "day": "2026-09-13", "kind": "auto_admit", "before": "0xeef6ad0e not in Z", "after": "in set Z, on probation", "detail": "75 settled paper copies, paper ROI +10.5%, trimmed +2.8%, ideal +18.1%", "push": "WALLET", "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c"}
{"ts": 1789317837.8643563, "day": "2026-09-13", "kind": "form", "before": "0xeef6ad0e unknown", "after": "benched", "detail": "0xeef6ad0e: no settled bets on our slice in 14 days", "push": null, "wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c"}
{"ts": 1789326749.006611, "day": "2026-09-13", "kind": "push:milestone", "before": null, "after": "🏁 <b>Bankroll crossed $100</b> upward: $111.56.", "detail": "", "push": "DEAL"}

## important lines (90)
2026-09-13 11:34:31 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 12:13:38 INFO  Received signal 15, shutting down...
2026-09-13 12:14:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-13 12:14:01 INFO  Bot started. Monitoring trades...
2026-09-13 12:59:55 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:02:04 ERROR [inventory] API sync failed: 
2026-09-13 13:12:22 INFO  Received signal 15, shutting down...
2026-09-13 13:13:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-13 13:13:10 INFO  Bot started. Monitoring trades...
2026-09-13 13:21:00 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:21:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:21:02 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:21:03 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:21:04 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 13:22:05 INFO  Received signal 15, shutting down...
2026-09-13 13:22:42 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-13 13:22:43 INFO  Bot started. Monitoring trades...
2026-09-13 13:48:20 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 14:00:14 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 14:05:47 ERROR [inventory] API sync failed: 
2026-09-13 14:18:27 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:18:28 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:18:29 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:22:46 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:22:47 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:22:48 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:22:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 14:29:50 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 14:46:50 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 14:51:24 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 15:00:29 INFO  Received signal 15, shutting down...
2026-09-13 15:00:52 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-13 15:00:52 INFO  Bot started. Monitoring trades...
2026-09-13 15:06:04 INFO  [ops] push:floor_near: None -> '⚠️ <b>Bankroll $62.30 is within 20% of the $56 floor.</b> A top-up of about $10 would restore the margin; under the floo'
2026-09-13 15:10:00 WARNING [live] ARMED for real orders by telegram: no reason given
2026-09-13 15:16:27 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 15:35:45 ERROR Network error fetching 0xfd3e...5a7a: Server disconnected without sending a response.
2026-09-13 15:35:45 ERROR Network error fetching 0x0587...c40b: Server disconnected without sending a response.
2026-09-13 15:35:45 ERROR Network error fetching 0x09b0...a3b6: Server disconnected without sending a response.
2026-09-13 15:35:48 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 15:41:49 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: The read operation timed out
2026-09-13 16:12:30 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $6.40 / $32.00
2026-09-13 16:12:32 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $6.40 / $200.00
2026-09-13 16:27:56 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 16:43:56 WARNING [zset] ADMITTED 0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c to set Z (+3% over 43 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-13 16:43:56 INFO  [ops] auto_admit: '0xeef6ad0e not in Z' -> 'in set Z, on probation' | 75 settled paper copies, paper ROI +10.5%, trimmed +2.8%, ideal +18.1%
2026-09-13 16:44:06 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:10 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:11 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:11 INFO  [ops] form: '0xeef6ad0e unknown' -> 'benched' | 0xeef6ad0e: no settled bets on our slice in 14 days
2026-09-13 16:44:12 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:13 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:44:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 16:51:18 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 16:52:30 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $12.80 / $32.00
2026-09-13 16:52:31 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $12.80 / $200.00
2026-09-13 16:54:05 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-13 16:57:00 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-13 17:57:07 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $6.40
2026-09-13 19:12:29 INFO  [ops] push:milestone: None -> '🏁 <b>Bankroll crossed $100</b> upward: $111.56.'
2026-09-13 19:17:31 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $0.00
2026-09-13 23:19:25 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-13 23:22:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 23:31:14 ERROR Network error fetching 0x1985...51ab: 
2026-09-13 23:31:55 ERROR [inventory] API sync failed: 
2026-09-14 00:08:24 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-14 00:08:24 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-14 00:08:24 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-14 00:08:24 ERROR Network error fetching 0x09b0...a3b6: 
2026-09-14 00:08:24 ERROR Network error fetching 0x0587...c40b: 
2026-09-14 08:01:21 INFO  [AB-RACE] rehearsal line sent, real-money line sent
2026-09-14 08:03:38 ERROR [inventory] API sync failed: 
2026-09-14 08:24:55 ERROR [inventory] API sync failed: 
2026-09-14 08:50:01 ERROR Network error fetching 0x09b0...a3b6: Server disconnected without sending a response.
2026-09-14 08:50:02 ERROR Network error fetching 0x3f3a...e8fd: Server disconnected without sending a response.
2026-09-14 08:50:02 ERROR Network error fetching 0x9f15...bdb3: Server disconnected without sending a response.
2026-09-14 08:50:03 ERROR Network error fetching 0xfd3e...5a7a: Server disconnected without sending a response.
2026-09-14 08:50:03 ERROR Network error fetching 0x0587...c40b: Server disconnected without sending a response.
2026-09-14 08:53:07 ERROR [inventory] API sync failed: 
2026-09-14 10:14:04 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-13 12:14:01 INFO  [recovery] No pending orders to recover
2026-09-13 13:13:10 INFO  [recovery] No pending orders to recover
2026-09-13 13:22:43 INFO  [recovery] No pending orders to recover
2026-09-13 15:00:52 INFO  [recovery] No pending orders to recover
2026-09-13 16:12:31 TRADE [LIVE] BUY $6.40 on 'LoL: LOUD vs paiN Gaming - Game 1 Winner' @ 0.3400, order 0x8150fdd57d...
2026-09-13 16:12:46 TRADE [verify] FILLED: BUY 18.82 shares on 'LoL: LOUD vs paiN Gaming - Game 1 Winner' @ 0.3400
2026-09-13 16:52:31 TRADE [LIVE] BUY $6.40 on 'SV 07 Elversberg vs. FC Bayern München: ' @ 0.8600, order 0xdc9394d059...
2026-09-13 16:52:34 TRADE [verify] FILLED: BUY 7.44 shares on 'SV 07 Elversberg vs. FC Bayern München: ' @ 0.8600
