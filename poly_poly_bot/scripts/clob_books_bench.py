"""Benchmark CLOB `get_order_books` call shapes for the tennis-arb
two-tier pricing refactor (BACKLOG.md).

Compares three shapes against a representative pool of ~40 live tennis
match-winner token_ids:
    A: 1 × get_order_books(40 tokens)
    B: 2 × get_order_books(20 tokens) in parallel
    C: 4 × get_order_books(10 tokens) in parallel

Each shape runs N iterations with a small inter-iteration sleep so
results don't share CDN/server-cache state. Records p50/p95/max latency
and any 4xx/5xx errors per shape.

Usage:
    .venv/bin/python scripts/clob_books_bench.py [--iters 10] [--sleep 3]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests
from py_clob_client_v2 import ClobClient
from py_clob_client_v2.clob_types import BookParams
from py_clob_client_v2.exceptions import PolyApiException


# Match-winner filter is intentionally narrow — we want representative
# tokens for the prod two-tier pricing path, which only ever calls the
# CLOB on H2H match-winners.
_DERIVATIVE_HINTS = (
    "o/u", "handicap", "set 1", "set 2", "set 3", "set winner",
    "total sets", "completed match", "grand slam", "will ",
)


def _looks_like_match_winner(question: str) -> bool:
    q = question.lower()
    if " vs " not in q and " vs. " not in q:
        return False
    return not any(h in q for h in _DERIVATIVE_HINTS)


def collect_tokens(target: int) -> list[tuple[str, str]]:
    """Walk Gamma's active tennis events and return up to `target`
    (question, token_id) pairs for currently-priceable match-winners.
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    offset = 0
    while len(found) < target and offset < 1000:
        resp = requests.get(
            "https://gamma-api.polymarket.com/events",
            params={
                "tag_slug": "tennis", "limit": 100, "offset": offset,
                "active": "true", "closed": "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json()
        if not events:
            break
        for ev in events:
            for m in ev.get("markets", []):
                q = m.get("question", "")
                if not _looks_like_match_winner(q):
                    continue
                try:
                    vol = float(m.get("volume", "0"))
                    liq = float(m.get("liquidity", "0"))
                except (TypeError, ValueError):
                    continue
                if vol < 50_000 or liq < 10_000:
                    continue
                try:
                    tokens = json.loads(m.get("clobTokenIds", "[]"))
                except (TypeError, ValueError):
                    continue
                for t in tokens:
                    if t and t not in seen:
                        seen.add(t)
                        found.append((q, t))
                        if len(found) >= target:
                            return found
        offset += 100
    return found


def verify_books_exist(client: ClobClient, tokens: list[str]) -> list[str]:
    """Drop tokens whose books 404 — the batched endpoint silently omits
    them, which would skew per-token cost downward."""
    keep: list[str] = []
    for t in tokens:
        try:
            client.get_order_book(t)
            keep.append(t)
        except PolyApiException:
            pass
    return keep


def time_one(call: Callable[[], None]) -> tuple[float, str | None]:
    t0 = time.perf_counter()
    try:
        call()
    except PolyApiException as e:
        return (time.perf_counter() - t0) * 1000, f"PolyApiException: {e}"
    except Exception as e:  # noqa: BLE001 — bench should never crash on one bad call
        return (time.perf_counter() - t0) * 1000, f"{type(e).__name__}: {e}"
    return (time.perf_counter() - t0) * 1000, None


def chunked(xs: list[str], n: int) -> list[list[str]]:
    """Split into roughly equal chunks of size n (last may be shorter)."""
    return [xs[i : i + n] for i in range(0, len(xs), n)]


def shape_single(client: ClobClient, tokens: list[str]) -> Callable[[], None]:
    params = [BookParams(token_id=t) for t in tokens]
    def go() -> None:
        client.get_order_books(params)
    return go


def shape_parallel(
    client: ClobClient, tokens: list[str], shards: int, pool: ThreadPoolExecutor,
) -> Callable[[], None]:
    chunk_size = (len(tokens) + shards - 1) // shards
    chunks = chunked(tokens, chunk_size)
    chunk_params = [[BookParams(token_id=t) for t in c] for c in chunks]
    def go() -> None:
        futs = [pool.submit(client.get_order_books, p) for p in chunk_params]
        for f in futs:
            f.result()
    return go


def summarize(name: str, samples: list[float], errors: list[str]) -> str:
    if not samples:
        return f"{name:>6s}: no samples"
    p50 = statistics.median(samples)
    p95 = statistics.quantiles(samples, n=20)[18] if len(samples) >= 20 else max(samples)
    mx = max(samples)
    mn = min(samples)
    err_n = sum(1 for e in errors if e)
    return (
        f"{name:>6s}: n={len(samples):3d}  "
        f"min={mn:6.1f}  p50={p50:6.1f}  p95={p95:6.1f}  max={mx:6.1f}  "
        f"errors={err_n}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=10, help="iterations per shape")
    ap.add_argument("--sleep", type=float, default=3.0,
                    help="seconds between iterations (CDN/cache decorrelation)")
    ap.add_argument("--target-tokens", type=int, default=40)
    args = ap.parse_args()

    print(f"=== CLOB get_order_books shape benchmark ===")
    print(f"target tokens: {args.target_tokens}  iters/shape: {args.iters}  "
          f"sleep: {args.sleep}s")
    print()

    client = ClobClient(host="https://clob.polymarket.com", chain_id=137)

    print("[1/3] Collecting candidate tokens from Gamma...")
    pairs = collect_tokens(args.target_tokens + 10)
    print(f"      got {len(pairs)} candidate tokens")
    print("[2/3] Verifying each token has a book (drops 404s)...")
    tokens = verify_books_exist(client, [t for _, t in pairs])
    tokens = tokens[: args.target_tokens]
    print(f"      using {len(tokens)} live tokens")
    print()

    if len(tokens) < 20:
        print(f"FATAL: only {len(tokens)} live tokens — not enough for the "
              "40/20/10 shape comparison. Aborting.")
        return 1

    # Adjust shapes to actual token count (don't crash if we have 28 instead of 40)
    n = len(tokens)
    shape_a = ("A:1×N", shape_single(client, tokens))

    print(f"[3/3] Running benchmark (n={n} tokens, {args.iters} iters each)...")
    print()

    # ThreadPoolExecutors must outlive the bench (Session + connection reuse)
    with ThreadPoolExecutor(max_workers=4) as pool:
        shape_b = (f"B:2×{(n + 1)//2}", shape_parallel(client, tokens, 2, pool))
        shape_c = (f"C:4×{(n + 3)//4}", shape_parallel(client, tokens, 4, pool))
        shapes = [shape_a, shape_b, shape_c]

        # Warm up — first call after a cold client has TLS + DNS cost
        # that distorts the first sample. Run a single throwaway iter
        # per shape before measurement.
        for name, fn in shapes:
            time_one(fn)

        # Interleave shapes per iteration so they all see comparable
        # server load / cache state across the run.
        per_shape: dict[str, list[float]] = {name: [] for name, _ in shapes}
        per_errors: dict[str, list[str]] = {name: [] for name, _ in shapes}

        for i in range(args.iters):
            for name, fn in shapes:
                dt, err = time_one(fn)
                per_shape[name].append(dt)
                per_errors[name].append(err or "")
                if err:
                    print(f"  iter {i+1:>2d} {name}: {dt:6.1f} ms  ERR: {err}")
                else:
                    print(f"  iter {i+1:>2d} {name}: {dt:6.1f} ms")
            time.sleep(args.sleep)

    print()
    print("=== Results ===")
    for name, _ in shapes:
        print("  " + summarize(name, per_shape[name], per_errors[name]))
    print()
    # Decision logic from BACKLOG.md
    p95s = {
        n: statistics.quantiles(s, n=20)[18] if len(s) >= 20 else max(s)
        for n, s in per_shape.items() if s
    }
    best = min(p95s, key=p95s.get)
    single_name = shape_a[0]
    gap = p95s[best] - p95s.get(single_name, p95s[best])
    print(f"Best p95: {best} ({p95s[best]:.1f} ms)")
    if best == single_name or abs(gap) < 100:
        print(f"→ SHIP shape A (1-way batched). Simpler code; no parallel "
              f"shape beats it by ≥100 ms.")
    else:
        print(f"→ SHIP shape {best}. It beats 1-way by "
              f"{p95s[single_name] - p95s[best]:.1f} ms at p95.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
