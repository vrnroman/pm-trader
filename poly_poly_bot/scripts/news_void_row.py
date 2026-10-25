"""Flag one news-bot paper row void (never delete it): it stays in the
ledger with its reason and leaves every count and number.

    python scripts/news_void_row.py <book> <row_id> "<reason>"
    python scripts/news_void_row.py <book> --find <substring>   # list matching row ids
"""
import sys

sys.path.insert(0, ".")
from src.newsbot.paper import PaperLedger  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    led = PaperLedger(argv[1])
    if argv[2] == "--find":
        for rid, r in led.rows.items():
            if argv[3] in rid:
                print(rid, r.decided_ts, r.entry_price, f"void={r.void!r}")
        return 0
    if len(argv) < 4:
        print(__doc__)
        return 2
    ok = led.void(argv[2], argv[3])
    print("voided" if ok else "no such row", argv[2])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
