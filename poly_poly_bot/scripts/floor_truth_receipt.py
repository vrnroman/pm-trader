"""The floor-row truth receipt: the backward row against the forward books.

Each set-Z wallet's floor row (backward replay: copy-and-hold at their price,
first entry, clean era) says which floor its edge favours. The forward paper
books B300, B150 and B100 copy at those floors with exits and drag, and since
2026-09-26 the shadow observer prices their copies too. So the row's chosen
floor can be checked, per wallet, against what the forward book AT THAT FLOOR
shows at real quotes. This prints agree / disagree / thin per wallet, a dated
retained baseline; the slice will be thin for weeks and the coverage line
says why. No verdict, no improvement claim.

Read-only. Run inside the bot container:

    python -m scripts.floor_truth_receipt [--out docs/floor-truth-<date>.md]
    (or python scripts/floor_truth_receipt.py)
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
import time

from src.config import CONFIG
from src.copy_trading import book_tiers, era_state, shadow_quote, virtual_ledger, wallet_floor, zset
from src.copy_trading.copy_paper import PaperCopyLedger



def _slice(wallet: str, positions, quotes: dict, era) -> dict:
    key = wallet.lower()
    mine = [p for p in positions if (getattr(p, "target", "") or "").lower() == key]
    return virtual_ledger.replay_positions(mine, quotes, min_opened_ts=era)


def receipt(now: float | None = None) -> tuple[str, dict]:
    now = time.time() if now is None else now
    era = era_state.era_floor_ts(os.path.join(CONFIG.data_dir, "ab_race_state.json"))
    quotes = virtual_ledger.quote_map(shadow_quote.load_rows())
    books = {b.id: (b, list(PaperCopyLedger(book_tiers.ledger_path(b, CONFIG)).positions.values()))
             for b in book_tiers.books(CONFIG)}
    z = sorted(zset.wallet_set())
    agree, disagree, thin, no_row = [], [], [], []
    lines = []
    for w in z:
        row = wallet_floor.stored(w)
        if not row:
            no_row.append(w)
            lines.append(f"  {w[:10]}  no floor row on the record yet")
            continue
        chosen = row.get("chosen")
        cell = (row.get("at") or {}).get(str(int(chosen))) if chosen else None
        fwd = None
        for bid, (b, pos) in books.items():
            if chosen is not None and float(b.min_usd) == float(chosen):
                fwd = (bid, _slice(w, pos, quotes, era))
        if chosen is None:
            lines.append(f"  {w[:10]}  row chooses nothing (global floor stays); "
                         + " · ".join(f"{k} n={c.get('n')}" for k, c in (row.get('at') or {}).items()))
            no_row.append(w)
            continue
        back = f"backward at ${chosen:.0f}: {cell['roi'] * 100:+.0f}% (trimmed {cell['trimmed'] * 100:+.0f}%, n={cell['n']})" if cell and cell.get("roi") is not None else f"backward at ${chosen:.0f}: n/a"
        if fwd is None:
            lines.append(f"  {w[:10]}  {back} · no forward book runs at ${chosen:.0f}")
            thin.append(w)
            continue
        bid, rq = fwd
        n, rr = int(rq.get("n_matched") or 0), rq.get("real_roi")
        if n < virtual_ledger.THIN_MATCHED_N or rr is None:
            lines.append(f"  {w[:10]}  {back} · forward {bid} at real quotes: thin ({n} of {virtual_ledger.THIN_MATCHED_N} matched, {rq.get('n_settled')} settled)")
            thin.append(w)
            continue
        verdict = "agree" if (rr >= 0) == (float(cell.get("roi") or 0) >= 0) else "DISAGREE"
        (agree if verdict == "agree" else disagree).append(w)
        lines.append(f"  {w[:10]}  {back} · forward {bid} at real quotes {rr * 100:+.0f}% over {n} matched · {verdict}")
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    text = (f"# Floor-row truth receipt, {day}\n\n"
            f"Per set-Z wallet: the floor row's chosen floor (backward replay, at their price) next to the forward "
            f"book at that floor priced at real quotes. Computed at {time.strftime('%H:%M UTC', time.gmtime(now))} "
            f"from the live ledgers; {len(quotes)} usable quotes. A retained baseline, not a verdict.\n\n"
            f"agree {len(agree)} · disagree {len(disagree)} · thin or no forward book {len(thin)} · no row or nothing chosen {len(no_row)}\n\n"
            + "\n".join(lines) + "\n\n" + shadow_quote.coverage_line() + "\n")
    return text, {"z": len(z), "agree": len(agree), "disagree": len(disagree), "thin": len(thin), "no_row": len(no_row)}


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
