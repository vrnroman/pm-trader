"""The rail swap receipt: what the execution rail changes at the Z door.

The owner ruled on 2026-09-26 (his doc, part 3 §3.1) that the real-quote
slice becomes the rail and book A the fallback while the slice is thin.
This prints, from the live ledgers and the observer's log, which wallets
the two rails disagree on, so the change is judged on data next to the
gate it replaces, and never as a "gate improved" claim:

* kept by both rails (pass under A, pass under the slice);
* admitted only by the slice (book A refused them, the slice does not);
* refused only by the slice (book A let them through, the slice refuses);
* set-Z wallets judged by the fallback today, with their matched counts.

Read-only. Run inside the bot container after the deploy:

    python -m scripts.rail_swap_receipt [--out docs/rail-swap-<date>.md]
    (or python scripts/rail_swap_receipt.py)

The output is a dated record, committed next to the requirements doc.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time

from src.copy_trading import zset
from src.copy_trading import zset_candidates as zc


def receipt(now: float | None = None) -> tuple[str, dict]:
    now = time.time() if now is None else now
    era, b_pos, a_pos = zc.load_books()
    quotes = zc.load_quotes(now)
    from src.copy_trading import promotion_gate
    corr = promotion_gate.split_half_corr(b_pos, min_opened_ts=era)
    counts: dict = {}
    for p in b_pos:
        w = (getattr(p, "target", "") or "").lower()
        if w and getattr(p, "closed", False):
            counts[w] = counts.get(w, 0) + 1
    from src.config import CONFIG
    wallets = sorted(w for w, n in counts.items() if n >= CONFIG.copy_golive_min_settled)
    in_z = zset.wallet_set()
    both, slice_only, a_only, z_fallback, thin = [], [], [], [], []
    for w in wallets:
        c = zc.evaluate(w, b_pos, a_pos, era=era, now=now, book_corr=corr, quotes=quotes)
        if c is None:
            continue
        other = [ok for lab, ok, _ in c.checks if lab not in (zset.SLICE_LABEL, zset.BOOK_A_LABEL)]
        rest_ok = all(other)
        a_ok, _ = zset.contradiction_check(c.a_roi, c.a_n, zc.CONTRADICTION_MIN_N)
        s_ok, s_detail, rail = zset.execution_check(c.real_roi, c.real_n, c.a_roi, c.a_n,
                                                    min_a_n=zc.CONTRADICTION_MIN_N)
        row = (w, c.real_n, c.real_roi, c.a_n, c.a_roi, rest_ok, w in in_z)
        if rail != zset.RAIL_SLICE:
            thin.append(row)
            if w in in_z:
                z_fallback.append(row)
            continue
        if a_ok and s_ok:
            both.append(row)
        elif s_ok and not a_ok:
            slice_only.append(row)
        elif a_ok and not s_ok:
            a_only.append(row)
    def fmt(rows):
        if not rows:
            return "  (none)\n"
        out = ""
        for w, rn, rr, an, ar, rest, z in rows:
            rr_s = f"{rr * 100:+.0f}%" if rr is not None else "n/a"
            ar_s = f"{ar * 100:+.0f}%" if ar is not None else "n/a"
            out += (f"  {w[:10]}  real quotes {rr_s} over {rn} matched · book A {ar_s} over {an}"
                    f" · other checks {'pass' if rest else 'fail'}{' · in Z' if z else ''}\n")
        return out
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    text = (f"# Rail swap receipt, {day}\n\n"
            f"The execution rail at the Z door: the real-quote slice (real ROI >= 0 over >= "
            f"{zset.REAL_QUOTE_MIN_N} matched) with book A as the fallback while the slice is thin. "
            f"Computed from the live ledgers at {time.strftime('%H:%M UTC', time.gmtime(now))}; "
            f"{len(wallets)} wallets with enough settled copies, {len(quotes)} usable quotes. "
            f"A retained baseline, not an improvement claim.\n\n"
            f"## Kept by both rails ({len(both)})\n{fmt(both)}\n"
            f"## Admitted only by the slice ({len(slice_only)}): book A refused them\n{fmt(slice_only)}\n"
            f"## Refused only by the slice ({len(a_only)}): book A let them through\n{fmt(a_only)}\n"
            f"## Slice thin, judged by book A ({len(thin)}); of them in set Z: {len(z_fallback)}\n{fmt(thin)}\n")
    summary = {"wallets": len(wallets), "both": len(both), "slice_only": len(slice_only),
               "a_only": len(a_only), "thin": len(thin), "z_fallback": len(z_fallback)}
    return text, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    text, _ = receipt()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
