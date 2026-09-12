# ops digest 2026-09-12T18:13:46.566675+00:00 (last 6h)

## money state
{"cash": 45.343671, "open_cost": 21.45, "equity": 66.79, "floor": 56.0, "stated": 80.0, "spend": {"date": "2026-09-12", "spent_usd": 21.45, "cap_usd": 500.0, "remaining_usd": 478.55}, "armed": true, "resolved_unclaimed": 66, "tier": {"1a": 0, "1b": 21.45, "1c": 0}, "ts": 1789236545.0136373, "day": "2026-09-12"}

## arm: {"armed": true, "ts": 1788698166.0465596, "by": "1shot:s-kac3t7", "reason": "owner: go activate bot, let go in; make sure deals are done (run s-kac3t7)", "first_armed_ts": 1788617432.0499406, "floor_override": false}
## spend today: {"date": "2026-09-12", "spent_usd": 21.45, "wallet_copies": {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": 2, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": 2}, "wallet_copies_yesterday": {}, "yesterday": "2026-09-11", "closed_reason": ""}
## set Z: {"0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd": {"wallet": "0x3f3aa7005f8006bfcc367d43a25cde25509fe8fd", "tier": "1b", "ts": 1786889554.1197178, "source": "gate"}, "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3": {"wallet": "0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3", "tier": "1b", "ts": 1788698181.3515182, "source": "telegram-gate"}, "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a": {"wallet": "0xfd3e6449d0c1e807501dcc17c0d9447201f35a7a", "tier": "1b", "ts": 1788698182.8017697, "source": "telegram-gate"}, "0x05878ac343c1387d592042d788424412733ac40b": {"wallet": "0x05878ac343c1387d592042d788424412733ac40b", "tier": "1b", "ts": 1789234932.162376, "source": "telegram-gate"}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"wallet": "0x09b045baad1fbe115c70785635a261411774a3b6", "tier": "1b", "ts": 1789234933.8880239, "source": "telegram-gate"}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab", "tier": "1b", "ts": 1789235975.528039, "source": "telegram-gate"}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709", "tier": "1b", "ts": 1789235977.260961, "source": "telegram-gate"}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35", "tier": "1b", "ts": 1789236561.2672133, "source": "telegram-gate"}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2", "tier": "1b", "ts": 1789236563.7443745, "source": "telegram-gate"}}
## tier exposure: {"1a": [0, 0], "1b": [21.45, 4], "1c": [0, 0]}
## probation: {"0x05878ac343c1387d592042d788424412733ac40b": {"since": 1789234925.3749237, "settled": 0}, "0x09b045baad1fbe115c70785635a261411774a3b6": {"since": 1789234925.3749237, "settled": 0}, "0x1985327e5782c62362dbbdf714c423d40d8f51ab": {"since": 1789235966.2959275, "settled": 0}, "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709": {"since": 1789235966.2959275, "settled": 0}, "0x5213eb85fcd465c8927a8382f95dd2dc22306a35": {"since": 1789236552.0468774, "settled": 0}, "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2": {"since": 1789236552.0468774, "settled": 0}}

## ledger (8 rows)
{"ts": 1789234914.4048996, "day": "2026-09-12", "kind": "push:floor_near", "before": null, "after": "⚠️ <b>Bankroll $66.83 is within 20% of the $56 floor.</b> A top-up of about $5 would restore the margin; under the floor", "detail": "", "push": "DEAL"}
{"ts": 1789234925.3749237, "day": "2026-09-12", "kind": "auto_admit", "before": "0x05878ac3 not in Z", "after": "in set Z, on probation", "detail": "52 settled paper copies, paper ROI +25.6%, trimmed +15.8%, ideal +26.6%", "push": "WALLET", "wallet": "0x05878ac343c1387d592042d788424412733ac40b"}
{"ts": 1789234925.3749237, "day": "2026-09-12", "kind": "auto_admit", "before": "0x09b045ba not in Z", "after": "in set Z, on probation", "detail": "46 settled paper copies, paper ROI +39.2%, trimmed +29.5%, ideal +40.2%", "push": "WALLET", "wallet": "0x09b045baad1fbe115c70785635a261411774a3b6"}
{"ts": 1789235966.2959275, "day": "2026-09-12", "kind": "auto_admit", "before": "0x1985327e not in Z", "after": "in set Z, on probation", "detail": "32 settled paper copies, paper ROI +63.3%, trimmed +40.5%, ideal +64.2%", "push": "WALLET", "wallet": "0x1985327e5782c62362dbbdf714c423d40d8f51ab"}
{"ts": 1789235966.2959275, "day": "2026-09-12", "kind": "auto_admit", "before": "0x4980930d not in Z", "after": "in set Z, on probation", "detail": "31 settled paper copies, paper ROI +35.8%, trimmed +15.4%, ideal +36.8%", "push": "WALLET", "wallet": "0x4980930da4ad1194d4f0fd5e29f17b70a42e5709"}
{"ts": 1789236308.5238607, "day": "2026-09-12", "kind": "escalation_delivered", "before": "routine escalation", "after": "sent", "detail": "Proof of the carry-down: this line was written to the ops-digest branch by the run s-g8int5 and reached you through the ", "push": "BOT"}
{"ts": 1789236552.0468774, "day": "2026-09-12", "kind": "auto_admit", "before": "0x5213eb85 not in Z", "after": "in set Z, on probation", "detail": "54 settled paper copies, paper ROI +16.6%, trimmed +0.9%, ideal +17.6%", "push": "WALLET", "wallet": "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"}
{"ts": 1789236552.0468774, "day": "2026-09-12", "kind": "auto_admit", "before": "0x57b25849 not in Z", "after": "in set Z, on probation", "detail": "82 settled paper copies, paper ROI +11.0%, trimmed +7.2%, ideal +12.0%", "push": "WALLET", "wallet": "0x57b258499f7a4cfc5043ceae57a51f7e6f529da2"}

## important lines (245)
2026-09-12 12:18:04 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:23:04 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:24:36 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-12 12:28:05 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:33:05 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:38:06 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:43:07 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:48:07 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:53:08 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 12:58:08 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:03:09 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:04:09 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 13:08:09 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:13:10 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:18:11 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:23:12 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:28:13 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:33:13 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:38:14 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:43:15 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:48:15 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:51:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 13:53:16 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 13:58:17 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:03:18 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:08:18 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:13:19 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:18:26 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:23:27 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:28:28 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:33:29 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:38:29 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:43:31 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:46:44 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 14:48:31 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:52:21 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 14:53:33 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 14:58:33 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:03:34 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:08:35 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:13:36 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:18:37 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:23:38 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:28:39 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:33:40 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:34:42 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 15:34:43 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 15:38:41 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:43:42 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:48:42 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:53:43 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 15:57:21 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 15:58:44 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:02:46 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 16:03:46 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:08:48 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:13:49 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:18:50 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:23:34 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 16:23:51 WARNING [guard] could not read equity for the floor: module 'src.copy_trading.live_budget' has no attribute 'note_collectable'
2026-09-12 16:24:09 INFO  Received signal 15, shutting down...
2026-09-12 16:25:36 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:25:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 16:25:39 INFO  Bot started. Monitoring trades...
2026-09-12 16:25:44 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:26:03 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:27:12 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:27:14 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:27:16 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:27:19 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:27:37 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:28:09 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:29:05 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:29:44 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:30:43 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:32:00 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:32:35 WARNING [tiered-risk] tier 1b carried a legacy open total $59.70 with no placements behind it: dropped
2026-09-12 16:32:49 INFO  [tiered-risk] Recorded tier 1b placement: $5.37 | open: $5.37 / $200.00
2026-09-12 16:32:49 INFO  [daily-cap] +$5.37 (copy:1b) | total today $5.37 / $26.87
2026-09-12 16:32:52 ERROR Network error fetching 0xfd3e...5a7a: Server disconnected without sending a response.
2026-09-12 16:32:52 ERROR Network error fetching 0x3f3a...e8fd: Server disconnected without sending a response.
2026-09-12 16:32:52 ERROR Network error fetching 0x9f15...bdb3: Server disconnected without sending a response.
2026-09-12 16:38:49 INFO  [tiered-risk] Recorded tier 1b placement: $5.37 | open: $10.74 / $200.00
2026-09-12 16:38:49 INFO  [daily-cap] +$5.37 (copy:1b) | total today $10.74 / $26.84
2026-09-12 16:38:57 INFO  Received signal 15, shutting down...
2026-09-12 16:39:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 16:39:39 INFO  Bot started. Monitoring trades...
2026-09-12 16:48:17 INFO  [tiered-risk] Recorded tier 1b placement: $5.36 | open: $16.10 / $200.00
2026-09-12 16:48:17 INFO  [daily-cap] +$5.36 (copy:1b) | total today $16.10 / $26.78
2026-09-12 16:48:54 INFO  Received signal 15, shutting down...
2026-09-12 16:49:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 16:49:37 INFO  Bot started. Monitoring trades...
2026-09-12 17:02:16 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:13:56 ERROR Network error fetching 0x3f3a...e8fd: 
2026-09-12 17:13:56 ERROR Network error fetching 0x9f15...bdb3: 
2026-09-12 17:13:56 ERROR Network error fetching 0xfd3e...5a7a: 
2026-09-12 17:20:36 INFO  Received signal 15, shutting down...
2026-09-12 17:21:20 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 17:21:21 INFO  Bot started. Monitoring trades...
2026-09-12 17:21:21 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 17:34:14 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:41:15 INFO  Received signal 15, shutting down...
2026-09-12 17:41:54 INFO  [ops] push:floor_near: None -> '⚠️ <b>Bankroll $66.83 is within 20% of the $56 floor.</b> A top-up of about $5 would restore the margin; under the floor'
2026-09-12 17:41:57 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 17:41:57 INFO  Bot started. Monitoring trades...
2026-09-12 17:42:12 WARNING [zset] ADMITTED 0x05878ac343c1387d592042d788424412733ac40b to set Z (+16% over 49 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 17:42:12 INFO  [ops] auto_admit: '0x05878ac3 not in Z' -> 'in set Z, on probation' | 52 settled paper copies, paper ROI +25.6%, trimmed +15.8%, ideal +26.6%
2026-09-12 17:42:13 WARNING [zset] ADMITTED 0x09b045baad1fbe115c70785635a261411774a3b6 to set Z (+29% over 43 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 17:42:13 INFO  [ops] auto_admit: '0x09b045ba not in Z' -> 'in set Z, on probation' | 46 settled paper copies, paper ROI +39.2%, trimmed +29.5%, ideal +40.2%
2026-09-12 17:42:30 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:42:31 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:42:32 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:42:33 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:45:37 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:47:57 ERROR [inventory] API sync failed: Client error '429 Too Many Requests' for url 'https://data-api.polymarket.com/positions?user=0xB5c5D02E8662b14691273a22aDd8E2f7F3DcdbF1'
2026-09-12 17:48:50 INFO  [tiered-risk] Recorded tier 1b placement: $5.35 | open: $21.45 / $200.00
2026-09-12 17:48:50 INFO  [daily-cap] +$5.35 (copy:1b) | total today $21.45 / $26.73
2026-09-12 17:58:37 INFO  Received signal 15, shutting down...
2026-09-12 17:59:19 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 17:59:20 INFO  Bot started. Monitoring trades...
2026-09-12 17:59:35 WARNING [zset] ADMITTED 0x1985327e5782c62362dbbdf714c423d40d8f51ab to set Z (+41% over 29 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 17:59:35 INFO  [ops] auto_admit: '0x1985327e not in Z' -> 'in set Z, on probation' | 32 settled paper copies, paper ROI +63.3%, trimmed +40.5%, ideal +64.2%
2026-09-12 17:59:37 WARNING [zset] ADMITTED 0x4980930da4ad1194d4f0fd5e29f17b70a42e5709 to set Z (+15% over 28 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 17:59:37 INFO  [ops] auto_admit: '0x4980930d not in Z' -> 'in set Z, on probation' | 31 settled paper copies, paper ROI +35.8%, trimmed +15.4%, ideal +36.8%
2026-09-12 17:59:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:59:43 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:59:44 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:59:45 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:59:46 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 17:59:47 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:01:01 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:05:11 INFO  [ops] escalation_delivered: 'routine escalation' -> 'sent' | Proof of the carry-down: this line was written to the ops-digest branch by the run s-g8int5 and reached you through the 
2026-09-12 18:08:23 INFO  Received signal 15, shutting down...
2026-09-12 18:09:07 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 18:09:08 INFO  Bot started. Monitoring trades...
2026-09-12 18:09:08 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=400 url=https://clob.polymarket.com/auth/api-key body={"error":"Could not create api key"}
2026-09-12 18:09:21 WARNING [zset] ADMITTED 0x5213eb85fcd465c8927a8382f95dd2dc22306a35 to set Z (+1% over 51 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 18:09:21 INFO  [ops] auto_admit: '0x5213eb85 not in Z' -> 'in set Z, on probation' | 54 settled paper copies, paper ROI +16.6%, trimmed +0.9%, ideal +17.6%
2026-09-12 18:09:23 WARNING [zset] ADMITTED 0x57b258499f7a4cfc5043ceae57a51f7e6f529da2 to set Z (+7% over 79 copies with its best 3 deleted). Real money may now follow it once armed.
2026-09-12 18:09:23 INFO  [ops] auto_admit: '0x57b25849 not in Z' -> 'in set Z, on probation' | 82 settled paper copies, paper ROI +11.0%, trimmed +7.2%, ideal +12.0%
2026-09-12 18:09:32 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:34 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:35 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:36 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:38 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:39 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:40 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 18:09:41 [py_clob_client_v2.http_helpers.helpers] ERROR: [py_clob_client_v2] request error status=404 url=https://clob.polymarket.com/price body={"error":"No orderbook exists for the requested token id"}
2026-09-12 12:14:26 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $2250.00 on 'Will Modena FC 2018 win on 2026-09-12?'
2026-09-12 12:14:26 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $2216.46 on 'Will Modena FC 2018 win on 2026-09-12?'
2026-09-12 12:14:45 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3104.76 on 'Will Modena FC 2018 win on 2026-09-12?'
2026-09-12 12:20:45 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3340.10 on 'Chelsea FC vs. Hull City AFC: O/U 3.5'
2026-09-12 12:21:39 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3104.76 on 'Will Modena FC 2018 win on 2026-09-12?'
2026-09-12 12:21:39 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $4327.27 on 'Will Genoa CFC vs. Frosinone Calcio end '
2026-09-12 12:22:06 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $5.94 on 'VfL Bochum vs. SpVgg Greuther Fürth: O/U'
2026-09-12 12:23:46 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $300.16 on 'Will Bayer 04 Leverkusen win on 2026-09-'
2026-09-12 12:23:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $763.08 on 'Will Bayer 04 Leverkusen win on 2026-09-'
2026-09-12 12:24:06 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3340.10 on 'Chelsea FC vs. Hull City AFC: O/U 3.5'
2026-09-12 12:27:37 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3104.76 on 'Will Modena FC 2018 win on 2026-09-12?'
2026-09-12 12:31:37 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1805.70 on 'Will Lillestrøm SK win on 2026-09-12?'
2026-09-12 12:31:51 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $3.76 on 'LoL: G2 NORD vs BIG - Game 1 Winner'
2026-09-12 12:41:31 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $1.08 on 'Will Wycombe Wanderers FC win on 2026-09'
2026-09-12 12:50:27 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $450.00 on 'Game Spread: Paquet (-3.5) vs Capurro (+'
2026-09-12 12:51:21 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $301.76 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:51:22 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $818.78 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:51:22 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $301.76 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:51:22 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $638.64 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:51:22 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $356.92 on 'Will West Ham United FC win on 2026-09-1'
2026-09-12 12:51:22 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $393.21 on 'Will West Ham United FC win on 2026-09-1'
2026-09-12 12:51:23 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $360.24 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:52:47 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $4.37 on 'Counter-Strike: Color vs SPARTA - Map 2 '
2026-09-12 12:53:55 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $4.30 on 'West Ham United FC vs. London City Lione'
2026-09-12 12:55:38 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1256.94 on 'Milton Keynes Dons FC vs. Peterborough U'
2026-09-12 13:02:21 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $3.94 on 'Counter-Strike: Saint Sinners vs mellren'
2026-09-12 13:04:59 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $0.72 on 'Counter-Strike: BetBoom Team vs G2 - Map'
2026-09-12 13:05:52 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $0.97 on 'Counter-Strike: BetBoom Team vs G2 - Map'
2026-09-12 13:10:54 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $31.26 on 'LoL: Anyone's Legend vs Invictus Gaming '
2026-09-12 13:11:32 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $1.77 on 'Real Racing Club vs. Deportivo Alavés: O'
2026-09-12 13:12:59 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $3.29 on 'LoL: Anyone's Legend vs Invictus Gaming '
2026-09-12 13:12:59 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $2.15 on 'Counter-Strike: BetBoom Team vs G2 - Map'
2026-09-12 13:14:32 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $300.03 on 'Will RSC Anderlecht Futures win on 2026-'
2026-09-12 13:15:03 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $2.14 on 'Counter-Strike: BBL vs Wildcard - Map 2 '
2026-09-12 13:21:21 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $29926.17 on 'Will Borussia Mönchengladbach win on 202'
2026-09-12 13:21:57 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $1.54 on 'Counter-Strike: BBL vs Wildcard (BO3) - '
2026-09-12 13:22:17 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $2.84 on 'Counter-Strike: BetBoom Team vs G2 - Map'
2026-09-12 13:23:13 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $0.86 on 'LoL: Anyone's Legend vs Invictus Gaming '
2026-09-12 13:24:11 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $1.40 on 'Counter-Strike: BBL vs Wildcard - Map 2 '
2026-09-12 13:26:18 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $0.84 on 'Counter-Strike: BBL vs Wildcard - Map 2 '
2026-09-12 13:26:19 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $3615.84 on 'Will Crystal Palace FC win on 2026-09-12'
2026-09-12 13:41:07 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1853.12 on 'Will SCR Altach win on 2026-09-12?'
2026-09-12 13:41:27 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $522.56 on 'Will Qatar SC win on 2026-09-12?'
2026-09-12 13:43:17 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $333.19 on 'Will Port Vale FC win on 2026-09-12?'
2026-09-12 13:45:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1853.12 on 'Will SCR Altach win on 2026-09-12?'
2026-09-12 13:55:32 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $2460.52 on 'Samsunspor vs. Çorum FK: O/U 2.5'
2026-09-12 14:00:09 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $63.00 on 'Cassis: Titouan Droguet vs Nicolai Budko'
2026-09-12 14:01:56 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1536.19 on 'Will Cesena FC vs. US Cremonese end in a'
2026-09-12 14:09:33 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $910.82 on 'Holy Cross vs. Miami (OH): O/U 47.5'
2026-09-12 14:10:08 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $11.77 on 'Spread: Blackpool FC (-2.5)'
2026-09-12 14:11:59 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1536.19 on 'Will Cesena FC vs. US Cremonese end in a'
2026-09-12 14:18:49 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $791.32 on 'Northern Colorado vs. Wyoming: O/U 46.5'
2026-09-12 14:23:12 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1536.19 on 'Will Cesena FC vs. US Cremonese end in a'
2026-09-12 14:24:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $2.30 on 'Counter-Strike: BetBoom Team vs G2 (BO3)'
2026-09-12 14:26:00 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $6.60 on 'Roda JC Kerkrade vs. Vitesse Arnhem: Vit'
2026-09-12 14:29:00 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $17.74 on 'Antalya 4: Alevtina Ibragimova vs Alicia'
2026-09-12 14:33:55 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1536.19 on 'Will Cesena FC vs. US Cremonese end in a'
2026-09-12 14:42:05 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1923.50 on 'Will Everton de Viña del Mar win on 2026'
2026-09-12 14:47:38 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $10.25 on 'Counter-Strike: MORROW vs megoshort - Ma'
2026-09-12 15:12:54 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $21.89 on 'CD Nacional vs. FC Alverca: O/U 2.5'
2026-09-12 15:12:54 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $13.65 on 'CD Nacional vs. FC Alverca: O/U 3.5'
2026-09-12 15:28:18 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $2993.82 on 'CD Nacional vs. FC Alverca: O/U 4.5'
2026-09-12 15:30:04 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $27.94 on 'LoL: Team Vitality vs Movistar KOI - Gam'
2026-09-12 15:31:18 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $6.27 on 'LoL: Team Vitality vs Movistar KOI - Gam'
2026-09-12 15:33:09 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $23.43 on 'LoL: Team Vitality vs Movistar KOI - Gam'
2026-09-12 15:35:04 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $7.67 on 'Counter-Strike: Iberian Soul vs M80 - Ma'
2026-09-12 15:37:56 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $5.36 on 'CA Osasuna vs. RCD Espanyol de Barcelona'
2026-09-12 15:37:56 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $4.92 on 'CA Osasuna vs. RCD Espanyol de Barcelona'
2026-09-12 16:01:19 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $5.14 on 'Dota 2: MOUZ vs Dawn Bulls - Game 2 Winn'
2026-09-12 16:06:31 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $7.43 on 'Counter-Strike: Quintessence vs TitanFlo'
2026-09-12 16:06:31 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: SELL $16.29 on 'Counter-Strike: Quintessence vs TitanFlo'
2026-09-12 16:07:00 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $740.00 on '1. FC Köln vs. SV Werder Bremen: O/U 2.5'
2026-09-12 16:10:37 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1368.18 on 'Girona FC vs. CD Castellón: O/U 2.5'
2026-09-12 16:11:46 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $2236.47 on 'Will FC Lugano win on 2026-09-12?'
2026-09-12 16:11:47 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1780.47 on 'Will FC Lugano win on 2026-09-12?'
2026-09-12 16:14:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1829.92 on 'Elche CF to score first vs. Athletic Clu'
2026-09-12 16:14:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1371.48 on 'Will AS Monaco FC win on 2026-09-12?'
2026-09-12 16:14:48 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $1240.36 on 'Will AS Monaco FC win on 2026-09-12?'
2026-09-12 16:15:06 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $470.29 on 'Athletic Club vs. Elche CF: O/U 2.5'
2026-09-12 16:19:09 SKIP  [exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96 < min_bet=$5.00: BUY $2434.15 on 'Tottenham Hotspur FC vs. Everton FC: Bot'
2026-09-12 16:25:39 INFO  [recovery] No pending orders to recover
2026-09-12 16:32:42 TRADE [LIVE] BUY $5.37 on 'Will Alanyaspor vs. Göztepe SK end in a ' @ 0.7200, order 0x750b63bfae...
2026-09-12 16:32:51 TRADE [verify] FILLED: BUY 7.46 shares on 'Will Alanyaspor vs. Göztepe SK end in a ' @ 0.7200
2026-09-12 16:38:45 TRADE [LIVE] BUY $5.37 on 'Will there be a run scored in the first ' @ 0.5000, order 0x8332f95ed8...
2026-09-12 16:38:51 TRADE [verify] FILLED: BUY 10.74 shares on 'Will there be a run scored in the first ' @ 0.5000
2026-09-12 16:39:38 INFO  [recovery] Recovering 1 pending order(s)...
2026-09-12 16:39:38 INFO  [recovery] Order 0x8332f95ed8... was FILLED (10.74 shares)
2026-09-12 16:39:39 INFO  [recovery] Pending order recovery complete
2026-09-12 16:48:07 TRADE [LIVE] BUY $5.36 on 'FC Lugano vs. Young Boys Bern: O/U 3.5' @ 0.5100, order 0xb3c1b2ce27...
2026-09-12 16:48:20 TRADE [verify] FILLED: BUY 10.51 shares on 'FC Lugano vs. Young Boys Bern: O/U 3.5' @ 0.5100
2026-09-12 16:49:37 INFO  [recovery] No pending orders to recover
2026-09-12 17:21:21 INFO  [recovery] No pending orders to recover
2026-09-12 17:41:57 INFO  [recovery] No pending orders to recover
2026-09-12 17:48:50 TRADE [LIVE] BUY $5.35 on 'Will FC Arda Kardzhali win on 2026-09-12' @ 0.8600, order 0x7639459795...
2026-09-12 17:48:51 TRADE [verify] FILLED: BUY 6.22 shares on 'Will FC Arda Kardzhali win on 2026-09-12' @ 0.8600
2026-09-12 17:59:19 INFO  [recovery] No pending orders to recover
2026-09-12 18:09:08 INFO  [recovery] No pending orders to recover
