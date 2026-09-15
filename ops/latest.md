# ops digest 2026-09-15T07:29:53.962693+00:00 (last 24h)

## money state
{"cash": 83.809781, "open_cost": 29.65, "equity": 113.46, "floor": 56.0, "stated": 80.0, "spend": {"date": "2026-09-15", "spent_usd": 0.0, "cap_usd": 32.0, "remaining_usd": 32.0, "closed_reason": ""}, "armed": true, "resolved_unclaimed": 63, "tier": {"1a": 0, "1b": 0, "1c": 0}, "ts": 1789457367.281486, "day": "2026-09-15"}

## arm: {"armed": true, "ts": 1789312200.3067093, "by": "telegram", "reason": "", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-15", "spent_usd": 0.0, "wallet_copies": {}, "wallet_copies_yesterday": {"0x05878ac343c1387d592042d788424412733ac40b": 1}, "yesterday": "2026-09-14", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x05878ac343c1387d592042d788424412733ac40b": {"wallet": "0x05878ac343c1387d592042d788424412733ac40b", "tier": "1b", "ts": 1789234932.162376, "source": "telegram-gate"}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "tier": "1b", "ts": 1789234933.8880239, "source": "telegram-gate"}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "tier": "1b", "ts": 1789235975.528039, "source": "telegram-gate"}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "tier": "1b", "ts": 1789235977.260961, "source": "telegram-gate"}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "tier": "1b", "ts": 1789236561.2672133, "source": "telegram-gate"}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2", "tier": "1b", "ts": 1789236563.7443745, "source": "telegram-gate"}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"wallet": "0x736539924a5602b37a03a54fc12c1cc8f98964da", "tier": "1b", "ts": 1789237156.0778086, "source": "telegram-gate"}, "0xd970693a3384dc762b191707a4927ac3814bbbba": {"wallet": "0xd970693a3384dc762b191707a4927ac3814bbbba", "tier": "1b", "ts": 1789237157.586524, "source": "telegram-gate"}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"wallet": "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c", "tier": "1b", "ts": 1789317836.75121, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [0, 0], "1c": [0, 0]}
## probation: {"0x05878ac343c1387d592042d788424412733ac40b": {"since": 1789234925.3749237, "settled": 0}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"since": 1789234925.3749237, "settled": 0}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"since": 1789235966.2959275, "settled": 0}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"since": 1789235966.2959275, "settled": 0}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"since": 1789236552.0468774, "settled": 0}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"since": 1789236552.0468774, "settled": 0}, "0x736539924a5602b37a03a54fc12c1cc8f98964da": {"since": 1789237149.0874667, "settled": 0}, "0xd970693a3384dc762b191707a4927ac3814bbbba": {"since": 1789237149.0874667, "settled": 0}, "0xeef6ad0e40c33f6703de88327f27f5e3d4aecd4c": {"since": 1789317835.1951635, "settled": 0}}
## form (each wallet on its own money, last 14 days, our slice)
in form  0x05878ac3: 163 settled, 55% won vs 47% needed, net +29.7% on $144,279, worst day -2,592
in form  0x09b045ba: 53 settled, 75% won vs 61% needed, net +19.1% on $20,290, worst day -306
in form  0x1985327e: 60 settled, 83% won vs 57% needed, net +24.8% on $23,540, worst day -159
benched  0x3f3aa700: 160 settled, 51% won vs 54% needed, net -1.2% on $414,324, worst day -39,107
benched  0x4980930d: 10 settled, 40% won vs 36% needed, net +63.9% on $11,693, worst day -1,364
benched  0x5213eb85: 94 settled, 46% won vs 38% needed, net -9.3% on $51,904, worst day -2,023
benched  0x57b25849: 66 settled, 47% won vs 46% needed, net -8.7% on $66,126, worst day -3,820
benched  0x73653992: 21 settled, 86% won vs 76% needed, net +58.4% on $37,084, worst day +108
benched  0x9f15613e: 203 settled, 51% won vs 50% needed, net +8.4% on $554,669, worst day -19,498
in form  0xd970693a: 64 settled, 75% won vs 56% needed, net +19.6% on $26,359, worst day +27
benched  0xeef6ad0e: no settled bets on our slice in 14 days
benched  0xfd3e6449: 15 settled, 73% won vs 76% needed, net +5.3% on $10,622, worst day -1,129

## ledger (0 rows)

## important lines (47)
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
2026-09-14 10:56:51 INFO  [daily-cap] +$6.40 (copy:1b) reserved | total today $6.40 / $32.00
2026-09-14 10:56:52 INFO  [tiered-risk] Recorded tier 1b placement: $6.40 | open: $6.40 / $200.00
2026-09-14 13:49:53 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-14 14:10:41 INFO  [tiered-risk] tier 1b: released $6.40 of exposure from resolved or closed positions | open now: $0.00
2026-09-14 16:02:56 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-14 16:37:20 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-14 16:55:06 ERROR [inventory] API sync failed: 
2026-09-14 16:59:19 ERROR Network error fetching 0x0587...c40b: 
2026-09-14 16:59:19 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-14 16:59:19 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-14 16:59:19 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-14 17:00:40 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-14 17:00:41 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-14 17:00:41 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-14 17:00:41 ERROR Network error fetching 0x09b0...a3b6: 
2026-09-14 17:00:41 ERROR Network error fetching 0x0587...c40b: 
2026-09-14 17:05:51 ERROR [inventory] API sync failed: 
2026-09-14 17:09:39 ERROR Network error fetching 0x4980...5709: 
2026-09-14 17:09:39 ERROR Network error fetching 0x5213...6a35: 
2026-09-14 17:09:39 ERROR Network error fetching 0x57b2...9da2: 
2026-09-14 17:09:41 ERROR Network error fetching 0x7365...64da: 
2026-09-14 17:09:42 ERROR Network error fetching 0x1985...51ab: Server disconnected without sending a response.
2026-09-14 17:37:13 ERROR Network error fetching 0x09b0...a3b6: Server disconnected without sending a response.
2026-09-14 18:16:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error: Server disconnected
2026-09-14 18:53:34 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-15 01:21:50 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-15 01:28:02 ERROR [inventory] API sync failed: 
2026-09-15 01:43:57 ERROR [inventory] API sync failed: Server disconnected without sending a response.
2026-09-15 01:48:50 ERROR Network error fetching 0x3f3a...e8fd: Server disconnected without sending a response.
2026-09-15 01:48:50 ERROR Network error fetching 0x9f15...bdb3: Server disconnected without sending a response.
2026-09-15 01:48:50 ERROR Network error fetching 0xfd3e...5a7a: Server disconnected without sending a response.
2026-09-15 01:48:51 ERROR Network error fetching 0x09b0...a3b6: Server disconnected without sending a response.
2026-09-15 01:48:51 ERROR Network error fetching 0x0587...c40b: Server disconnected without sending a response.
2026-09-15 04:19:55 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-15 04:25:03 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-14 10:56:51 TRADE [LIVE] BUY $6.40 on 'LoL: Dplus KIA Challengers vs KT Rolster' @ 0.4300, order 0x7e6632c574...
2026-09-14 10:56:52 TRADE [verify] FILLED: BUY 14.88 shares on 'LoL: Dplus KIA Challengers vs KT Rolster' @ 0.4300
