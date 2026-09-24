#!/usr/bin/env python3
"""The experiment process: a control and a treatment paper book, one feed.

Started by the analyst's supervisor (scripts/ai_analyst.py) for the one
live card, as a CHILD PROCESS of the sidecar, never inside it: a code
change under test is imported by this process alone, from the card's
clone. The fence (manager, s-ye5990):

- no trading key, no Telegram token, live arm off (the parent strips them);
- ``DATA_DIR`` points at ``<card dir>/scratch`` so every incidental write of
  the harness lands under the card, never in the bot's data dir; the real
  data dir is read for the watchlists, the gate history and B's blacklist;
- an address-space limit (EXP_MAX_RSS_MB) so a runaway experiment dies
  before the sidecar does; the diff itself is screened for forbidden paths
  and words before it lands (ai_analyst.EXP_FORBIDDEN*). This is an
  environment fence, not a kernel one: the child shares the sidecar's uid
  and mounts. A third container with the data dir read-only would be the
  real boundary; that is the owner's call.
- the control IS book B (``book_recipes.book_b_kwargs``); the treatment is
  the same recipe plus the card's knobs, and, for a code change, the card's
  flag turned on around its cycle only (``exp_flag``). Both read one
  ``TradeFeed`` so they see the same fills.

It writes ``control.jsonl``, ``treatment.jsonl`` and ``heartbeat.json`` in
the card's directory and stops on its own when the card is no longer live.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FEED_TTL_S = 120.0
DEFAULT_MAX_RSS_MB = 400.0
DEFAULT_REAL_DATA_DIR = os.environ.get("EXP_REAL_DATA_DIR", "/app/data")


def fence(max_mb: float) -> str:
    """Cap the address space. Returns what happened (some platforms refuse).
    Zero or less is no cap: a cap of 0 bytes would starve this very process
    (it did, to the CI runner's pytest, on 2026-09-24)."""
    if max_mb <= 0:
        return "address space cap off"
    try:
        import resource
        lim = int(max_mb * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
        return f"address space capped at {max_mb:.0f} MB"
    except (ImportError, ValueError, OSError) as exc:
        return f"address space cap not applied: {exc!r}"


def rss_mb() -> float:
    try:
        import resource
        v = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return v / 1024.0 if sys.platform.startswith("linux") else v / (1024.0 * 1024.0)
    except (ImportError, OSError):
        return 0.0


def read_card(card_path: str) -> dict:
    try:
        with open(card_path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def blacklist_reader(real_data_dir: str, now: Callable[[], float] = time.time) -> Callable[[], set]:
    """B's own blacklist, read from the real data dir by the same rule
    ``promotion_state.active_blacklist`` applies (a record is active while
    ``until`` is 0 or in the future). Read-only."""
    p = os.path.join(real_data_dir, "copy_blacklist_b.json")

    def read() -> set:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return set()
        recs = d.get("wallets", d) if isinstance(d, dict) else {}
        out: set = set()
        t = now()
        for w, rec in (recs or {}).items():
            until = float((rec or {}).get("until") or 0.0) if isinstance(rec, dict) else 0.0
            if until <= 0.0 or t < until:
                out.add(str(w).lower())
        return out
    return read


def build(card: dict, card_dir: str, *, real_data_dir: str = DEFAULT_REAL_DATA_DIR,
          feed=None, book_fetcher=None, resolver=None, detector_factory=None,
          exit_detector_factory=None, blacklist_provider=None, now: Callable[[], float] = time.time):
    """``(control, treatment)`` runners. Paths are explicit: ledgers and era
    files under the card, watchlists and the gate history from the real
    data dir. Tests inject the feed and fetchers."""
    from src.config import CONFIG
    from src.copy_trading.book_recipes import book_b_kwargs
    from src.copy_trading.copy_paper_runner import CopyPaperRunner
    from src.copy_trading.copy_paper_live import (TradeFeed, fetch_asks, make_feed_detector,
                                                  make_feed_exit_detector, resolve)
    base = book_b_kwargs(CONFIG)
    base["watchlist_path"] = os.path.join(real_data_dir, os.path.basename(base["watchlist_path"]))
    base["extra_watchlist_paths"] = [os.path.join(real_data_dir, os.path.basename(p)) for p in base["extra_watchlist_paths"]]
    base["gate_history_path"] = os.path.join(real_data_dir, "gate-history.jsonl")
    knobs = dict(card.get("knobs") or {})
    treat = {**base, **knobs}
    floor = min(float(CONFIG.copy_paper_feed_min_usd), float(treat.get("min_usd") or base["min_usd"]))
    feed = feed if feed is not None else TradeFeed(ttl_s=FEED_TTL_S)

    def _det(wallets, max_age_s, min_usd, flagged_by_map=None, **kw):
        if detector_factory is not None:
            return detector_factory(wallets, max_age_s, min_usd, flagged_by_map, **kw)
        return make_feed_detector(wallets, max_age_s, min_usd, flagged_by_map, feed=feed, feed_min_usd=floor, **kw)

    def _exit(wallets, max_age_s):
        if exit_detector_factory is not None:
            return exit_detector_factory(wallets, max_age_s)
        return make_feed_exit_detector(wallets, max_age_s, feed=feed, feed_min_usd=floor)

    common = dict(
        blacklist_provider=blacklist_provider or blacklist_reader(real_data_dir, now=now),
        detector_factory=_det, exit_detector_factory=_exit,
        book_fetcher=book_fetcher or fetch_asks, resolver=resolver or resolve,
    )
    control = CopyPaperRunner(**{**base, "ledger_path": os.path.join(card_dir, "control.jsonl"),
                                 "era_state_path": os.path.join(card_dir, "era-control.json")}, **common)
    treatment = CopyPaperRunner(**{**treat, "ledger_path": os.path.join(card_dir, "treatment.jsonl"),
                                   "era_state_path": os.path.join(card_dir, "era-treatment.json")}, **common)
    return control, treatment


def cycle(card: dict, control, treatment) -> tuple[object, object]:
    """One control cycle, then one treatment cycle with the card's flag on
    (and off again whatever happens). Returns both summaries."""
    from src.copy_trading import exp_flag
    a = control.run_once()
    with exp_flag.enabled(card.get("flag") or ""):
        b = treatment.run_once()
    return a, b


def write_heartbeat(card_dir: str, *, cycles: int, now: float, note: str = "") -> None:
    p = os.path.join(card_dir, "heartbeat.json")
    try:
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"ts": now, "pid": os.getpid(), "cycles": cycles, "rss_mb": round(rss_mb(), 1), "note": note}, f)
        os.replace(p + ".tmp", p)
    except OSError:
        pass


def run(card_path: str, *, real_data_dir: str = DEFAULT_REAL_DATA_DIR, max_cycles: Optional[int] = None,
        interval_s: Optional[float] = None, sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time, log: Callable[[str], None] = print, **inject) -> int:
    """The loop. Stops when the card is not live, after ``max_cycles``, or
    on a fatal build error. Returns the cycle count."""
    card_dir = os.path.dirname(os.path.abspath(card_path))
    card = read_card(card_path)
    if not card.get("id"):
        log(f"[exp] no card at {card_path}")
        return 0
    if card.get("status") != "live":
        log(f"[exp] {card['id']} is {card.get('status')}, nothing to run")
        return 0
    control, treatment = build(card, card_dir, real_data_dir=real_data_dir, **inject)
    every = float(interval_s if interval_s is not None else control.cycle_interval_s or 60)
    log(f"[exp] {card['id']}: control = book B, treatment = B + {card.get('knobs') or {}}"
        f"{' + flag ' + card['flag'] if card.get('flag') else ''}; {len(control.wallets())} wallets; every {every:.0f}s")
    cycles = 0
    while True:
        card = read_card(card_path) or card
        if card.get("status") != "live":
            write_heartbeat(card_dir, cycles=cycles, now=now(), note=f"stopped: card is {card.get('status')}")
            log(f"[exp] {card.get('id')} is {card.get('status')}: stopping")
            break
        try:
            a, b = cycle(card, control, treatment)
            cycles += 1
            if getattr(a, "opened", 0) or getattr(b, "opened", 0) or getattr(a, "resolved", 0) or getattr(b, "resolved", 0):
                log(f"[exp] cycle {cycles}: control opened {getattr(a, 'opened', 0)} resolved {getattr(a, 'resolved', 0)}; "
                    f"treatment opened {getattr(b, 'opened', 0)} resolved {getattr(b, 'resolved', 0)}")
            write_heartbeat(card_dir, cycles=cycles, now=now())
        except Exception as exc:  # noqa: BLE001  the loop survives a bad cycle
            log(f"[exp] cycle failed: {exc!r}")
            write_heartbeat(card_dir, cycles=cycles, now=now(), note=f"cycle failed: {exc!r}"[:200])
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep(every)
    return cycles


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--card", required=True, help="path to the card.json")
    ap.add_argument("--real-data-dir", default=DEFAULT_REAL_DATA_DIR)
    ap.add_argument("--max-rss-mb", type=float, default=float(os.environ.get("EXP_MAX_RSS_MB", DEFAULT_MAX_RSS_MB)))
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--interval", type=float, default=None)
    a = ap.parse_args(argv)
    for k in ("PRIVATE_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CLAUDE_CODE_OAUTH_TOKEN"):
        if os.environ.get(k):
            print(f"[exp] refusing to run with {k} in the environment", flush=True)
            return 2
    print(f"[exp] {fence(a.max_rss_mb)}", flush=True)
    from src.logger import logger
    run(a.card, real_data_dir=a.real_data_dir, max_cycles=a.max_cycles, interval_s=a.interval,
        log=lambda s: logger.info(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
