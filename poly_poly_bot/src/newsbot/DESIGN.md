# newsbot: a news-driven Polymarket paper trader (run s-pw9rom, 2026-10-25)

Replaces the copy bot's threads in the same container (`NEWS_MODE=1`). Paper
only. Free sources only. The LLM is `claude -p` on the owner's subscription,
called only after a deterministic shortlist exists, and bounded per day.

The thesis to test in two weeks: do free sources lead Polymarket's price, by
domain, and does a $5 paper copy at the honest ask, exited at +5m/+30m/+2h/
+24h, make money after fees? The instrument matters more than the book: every
item carries four clocks and every price move carries its first free mention
(or "dark").

## Packages (all under `src/newsbot/`)

- `items.py`: the `Item` dataclass and the dedup store.
- `sources/`: one module per source family; each exposes `poll(state) -> list[Item]`
  (HTTP) or `async stream(queue)` (websocket). Families: `rss.py` (RSS/Atom incl.
  SEC 8-K Atom and trumpstruth), `telegram_web.py` (t.me/s/<channel> HTML),
  `bluesky.py` (Jetstream websocket, DID list resolved at boot from handles),
  `treeofalpha.py` (JSON), `hn.py` (Algolia). `roster.py` holds the source list
  with domain tags and poll intervals (env-overridable), and the per-source
  counters (items, mapped, fired, errors, last_ok_ts).
- `tape/`: `livedata.py` (Polymarket live-data websocket: every trade and comment;
  bucketed per conditionId per minute: n, notional, first/last price, delta;
  never stores raw frames), `clob_ws.py` (CLOB market websocket for subscribed
  token ids: best bid/ask ring buffer, last 30 min), `jumps.py` (jump detector
  over the buckets: a market whose price moved > JUMP_CENTS within JUMP_WINDOW_MIN,
  excluding tags in TAPE_EXCLUDE_TAGS such as 5-minute crypto up/down and sports).
- `index.py`: the market universe from Gamma (active, not closed, volume floor),
  refreshed every 10 min, in SQLite FTS5 (title, question, description, event
  title, tags, outcomes); `candidates(text, k)` returns the top-k markets with
  their token ids, tags, current best bid/ask (from Gamma fields), and
  domain labels. Tag -> domain map is a static table in the module.
- `judge.py`: the one LLM call. Input: an Item plus its FTS candidates with
  current prices and the tape freshness per candidate. Output (strict JSON):
  `{material: bool, market_id|null, outcome_index|null, direction: "yes"|"no"|null,
  implied_prob: float|null, confidence: 0..1, why: str, already_priced: bool}`.
  Runs through `llm.py` (`claude -p --output-format json --model <JUDGE_MODEL>`),
  one bounded retry, RATE_LIMITED sentinel, per-day call budget `LLM_DAILY_BUDGET`
  (default 150); over budget -> item logged as `skipped:budget`, never fired.
  `already_priced` from the LLM is advisory only; the tape rule decides (below).
- `freshness.py`: the tape rule. `verdict(token_id, now) -> ("fresh"|"moving"|"late"|"unknown", detail)`:
  fresh = no |move| > FRESH_CENTS in the last FRESH_MIN minutes on that token and
  the ask is within FRESH_CENTS of the 15-min pre-window mid; moving = a move is
  in progress now (the item is late; log, do not fire); unknown = no tape yet.
- `paper.py`: the paper book. A fire books a `$STAKE` BUY at the honest ask walked
  from the CLOB book (depth at our size recorded, fee charged: rate x p x (1-p)
  per share from `fee_rate`), then marks at +5m/+30m/+2h/+24h with the honest bid
  (walked for our size) and books four exit P&Ls plus hold-to-resolution. Two
  control books ride the same items: `headline-any` (fires on every mapped item,
  no freshness rule) and `random` (same count of fires per day on random active
  markets, same stake). JSONL ledgers under `data/news/`.
- `leads.py`: the lead-time ledger. For each jump: candidate items in the prior
  LEAD_LOOKBACK_MIN from every source whose text shares tokens with the market
  title; the LLM picks the explaining item or says none -> `dark`. Rows:
  `{jump_ts, market, delta, first_source, first_source_ts, lead_s (source first = positive), dark: bool}`.
  Per item that fired or mapped: `t_published, t_seen, t_decided, t_quote, moved_5m/30m/2h/24h`.
- `brief.py`: the 08:00 UTC one-line brief plus a collapsed ledger; `/news`
  Telegram command (current book, today's fires, the 2x2, the dark fraction by
  domain, the roster's counters); surprise pings (a mapped market moved > N cents
  and we did not fire; a source silent > SILENT_HOURS). All sends go through
  `telegram_bot.send_message(kind=...)`.
- `runner.py`: the asyncio supervisor: starts the sockets, the pollers, the
  index refresher, the exit marker, the brief scheduler; structured one-line
  logs `[news] ...` per stage; idempotent restart (dedup store on disk, open
  paper rows re-marked from their own timestamps, no double fires).

## Item schema

```
Item(id: str,            # f"{source}:{native_id}" ; dedup key
     source: str,        # roster key, e.g. "tg:financialjuice", "bsky:reuters.com", "rss:nyt-home", "sec:8k", "toa", "hn"
     domains: tuple,     # from the roster: ("geo",), ("corp",), ("crypto",), ("politics",), ("ent",)
     published_ts: float,  # the SOURCE's own timestamp (UTC epoch), never ours
     seen_ts: float,       # when we received it
     title: str, text: str, url: str)
```

## Clocks and verdicts (what the two-week report prints)

- Per domain: items, mapped, fired, fired-and-moved-our-way (> MOVE_CENTS within 24h),
  moved-before-seen (late), never-moved; median our latency (seen -> decided);
  median market repricing lag (published -> first tape move); dark fraction of jumps.
- Books: LLM book vs headline-any vs random, each at the honest ask with fees,
  per exit horizon, n and +/- 1 SD. "Best exit" is printed as an estimate.
- Every number carries n. Empty renders as "collecting, n=0".

## Env knobs (deploy.yml ensure_env, defaults in code)

NEWS_MODE=1, NEWS_STAKE_USD=5, NEWS_JUDGE_MODEL=claude-sonnet-4-5, NEWS_LLM_DAILY_BUDGET=150,
NEWS_FRESH_CENTS=3, NEWS_FRESH_MIN=15, NEWS_JUMP_CENTS=8, NEWS_JUMP_WINDOW_MIN=10,
NEWS_MOVE_CENTS=5, NEWS_DOMAINS=politics,crypto,geo,corp, NEWS_OBSERVE_ONLY=0,
NEWS_BRIEF_UTC=08:00, NEWS_SILENT_HOURS=6, NEWS_INDEX_VOLUME_MIN=5000.

## Standing rules carried from the copy bot (handoff.md)

Never trust a client's collection ordering (CLOB bids ascending / asks descending).
Report the test count the run printed. A sample count counts independent
observations. Unknown is not zero on a ledger. Guard the production call site,
not the helper. Empty renders as "collecting, n=0".

## Manager rulings (run s-pw9rom, 2026-10-25; scratchpad ideation/manager1.md)

- Paper-fire from day 1 on every mapped item that passes the tape rule; the
  lead ledger and the control books run alongside. No observe-only week.
- Books: `llm` (main: judge says material + tape fresh), `tape-first` (a jump
  confirmed by a news item within 5 min), `headline-any` (every mapped item,
  no freshness rule), `random` (same fires per UTC day on random markets).
  One exit grid for all books; "best exit" is an estimate in the brief.
- Phone: per-fire message with headline, market, honest ask, depth, the tape's
  freshness line; NO confidence number (it stays in the ledger). Timed exits
  are never pinged; they land in the 08:00 UTC brief. Surprise pings by a rules
  table: a mapped market moved > NEWS_MOVE_CENTS and we did not fire; a source
  silent > NEWS_SILENT_HOURS; the box quiet. /news for the current book.
- LLM: one model, one call per item, mapping only (no second pass on fires).
  `NEWS_JUDGE_MODEL` default `claude-sonnet-5-5`; hard daily cap
  `NEWS_LLM_DAILY_BUDGET` default 300; RATE_LIMITED = defer, never fire.
- NEWS_MODE: copy threads not started, code stays in the tree; the live guard /
  redeemer / settlement booking for the positions still held keeps running;
  no real-order path is reachable; copy commands answer "retired in NEWS_MODE".
  Deleting the copy code is a decide item at the two-week review.
- Domains: politics (Trump, the positive control), crypto minus 5-minute up/down
  markets, geopolitics, corporate (8-K). Entertainment and sports out.
- Deploy: the repo's norm (PR, full suite + clock-drift run, merge, gh run watch,
  confirm the container and the first socket message). Auto tier.
- Deferred: #12 LLM roster grader [scope, trigger: deterministic ranking
  ambiguous at the two-week read]; #19 public scoreboard [owner].
