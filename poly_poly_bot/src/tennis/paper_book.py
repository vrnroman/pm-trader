"""Paper-trading book for Strategy #3 (Tennis Arb).

Tracks notional positions opened by tennis-arb signals and computes realized
+ unrealized PnL with a per-event breakdown. Designed so a contradicting
signal on the same Polymarket market closes the existing YES position
(selling YES at the current implied PM price) and opens a new YES position
on the now-favored side, instead of opening a fresh NO position that would
tie up additional capital.

State persists to ``data/tennis_paper_book.json`` with atomic writes.

Position lifecycle
------------------
- OPEN: a signal arrives for a market we have no open position on. We buy
  ``shares = bet_size_usd / entry_price`` of YES on the favored player's
  Polymarket token.
- HOLD: a signal arrives for a market where we already hold YES on the
  *same* token. The existing rebet-gate in ``tennis_arb.py`` already
  filters out duplicate signals unless the edge has grown materially; if
  one still gets through we treat it as "already long" and don't stack.
- FLIP: a signal arrives for a market where we hold YES on the *opposite*
  player's token. We close the existing position at the implied current
  PM price for our side (``1 - new_signal_price``, since YES_A + YES_B ≈ 1
  in a binary Polymarket market) and then open a new YES position on the
  now-favored side. Realized PnL on the close is recorded with
  ``exit_reason = "FLIP"``.
- RESOLVED: when a Polymarket market settles, open positions on that
  market close at exit_price 1.0 (winning side) or 0.0 (losing side).
  Discovered by ``tennis_arb.py`` polling Gamma per open condition_id.

PnL math
--------
::

    shares = bet_size_usd / entry_price
    realized_pnl_usd   = shares * (exit_price    - entry_price)
    unrealized_pnl_usd = shares * (current_price - entry_price)

Worked example: enter YES on A at 0.50 with $7.

- shares = 14.0
- Sell at 0.62 → realized = 14.0 × (0.62 - 0.50) = +$1.68
- At resolution, A wins → realized = 14.0 × (1.00 - 0.50) = +$7.00
- At resolution, A loses → realized = 14.0 × (0.00 - 0.50) = -$7.00
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from src.logger import logger


_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TennisPaperBook:
    """Paper-trading state machine for tennis-arb signals."""

    def __init__(self, data_dir: str):
        self._path = os.path.join(data_dir or ".", "tennis_paper_book.json")
        self._lock = threading.Lock()
        self._state = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("paper book file is not a dict")
            data.setdefault("version", _SCHEMA_VERSION)
            data.setdefault("open_positions", {})
            data.setdefault("closed_positions", [])
            return data
        except FileNotFoundError:
            return {"version": _SCHEMA_VERSION, "open_positions": {}, "closed_positions": []}
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.error(f"[paper-book] failed to load {self._path}: {exc} — starting fresh")
            return {"version": _SCHEMA_VERSION, "open_positions": {}, "closed_positions": []}

    def _save(self) -> None:
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Position lookup
    # ------------------------------------------------------------------
    def _open_on_condition(self, condition_id: str) -> dict | None:
        """Return the (single) open position for this condition_id, or None.

        Paper book holds at most one open position per market. Same-direction
        signals are skipped (HOLD); opposite-direction signals trigger a FLIP.
        """
        if not condition_id:
            return None
        for pos in self._state["open_positions"].values():
            if pos.get("condition_id") == condition_id:
                return pos
        return None

    # ------------------------------------------------------------------
    # Signal entry point
    # ------------------------------------------------------------------
    def process_signal(self, signal: dict) -> dict:
        """Apply a tennis-arb signal to the book.

        Returns an action summary::

            {"action": "OPEN" | "FLIP" | "HOLD",
             "position_id": str,
             "closed_position_id": str | None,
             "realized_pnl_usd": float | None}
        """
        with self._lock:
            condition_id = signal.get("condition_id") or ""
            new_token = signal.get("token_id") or ""
            entry_price = float(signal.get("polymarket_price") or 0.0)
            size_usd = float(signal.get("bet_size") or 0.0)

            existing = self._open_on_condition(condition_id)

            if existing is None:
                if entry_price <= 0 or size_usd <= 0:
                    # Defensive: a degenerate signal shouldn't sneak in but
                    # if it does we don't want to crash the scanner.
                    logger.warn(
                        f"[paper-book] skipping signal with non-positive "
                        f"price/size: {entry_price} / {size_usd}"
                    )
                    return {
                        "action": "HOLD",
                        "position_id": "",
                        "closed_position_id": None,
                        "realized_pnl_usd": None,
                    }
                pos = self._open(signal)
                self._save()
                logger.info(
                    f"[paper-book] OPEN {pos['outcome_player']} YES @ "
                    f"{pos['entry_price']:.3f} size=${pos['size_usd']:.2f} "
                    f"({pos['shares']:.3f} shares)"
                )
                return {
                    "action": "OPEN",
                    "position_id": pos["id"],
                    "closed_position_id": None,
                    "realized_pnl_usd": None,
                }

            if existing["token_id"] == new_token:
                # Same direction; the rebet gate already filtered upstream.
                # Keep the original entry to keep PnL accounting unambiguous
                # (no DCA into the position).
                return {
                    "action": "HOLD",
                    "position_id": existing["id"],
                    "closed_position_id": None,
                    "realized_pnl_usd": None,
                }

            # FLIP: opposite direction on the same market. PM is binary so
            # YES_A + YES_B ≈ 1; the new signal carries the favored side's
            # current YES price, which means the *current* price for our
            # existing (now-disfavored) side is approximately 1 - new_price.
            # That's the price we'd realize if we sold YES on the existing
            # side now.
            opposite_close_price = max(0.0, min(1.0, 1.0 - entry_price))
            closed = self._close(existing, exit_price=opposite_close_price, reason="FLIP")
            new_pos = self._open(signal)
            self._save()
            logger.info(
                f"[paper-book] FLIP closed {closed['outcome_player']} @ "
                f"{closed['exit_price']:.3f} → realized "
                f"${closed['realized_pnl_usd']:+.2f}; opened "
                f"{new_pos['outcome_player']} YES @ {new_pos['entry_price']:.3f} "
                f"size=${new_pos['size_usd']:.2f}"
            )
            return {
                "action": "FLIP",
                "position_id": new_pos["id"],
                "closed_position_id": closed["id"],
                "realized_pnl_usd": closed["realized_pnl_usd"],
            }

    # ------------------------------------------------------------------
    # Open / close primitives
    # ------------------------------------------------------------------
    def _open(self, signal: dict) -> dict:
        entry_price = float(signal.get("polymarket_price") or 0.0)
        size_usd = float(signal.get("bet_size") or 0.0)
        # process_signal guards against this for the OPEN path; we keep the
        # check here too because _open is also reached from FLIP.
        if entry_price <= 0 or size_usd <= 0:
            raise ValueError(
                f"can't open paper position with non-positive entry "
                f"(price={entry_price}, size={size_usd})"
            )
        shares = round(size_usd / entry_price, 6)
        position_id = uuid.uuid4().hex[:12]
        position = {
            "id": position_id,
            "opened_at": _now_iso(),
            "status": "OPEN",
            "side": "YES",
            "condition_id": signal.get("condition_id") or "",
            "token_id": signal.get("token_id") or "",
            "market_id": signal.get("market_id") or "",
            "event_title": signal.get("event_title") or "",
            "event_slug": signal.get("event_slug") or "",
            "polymarket_url": signal.get("polymarket_url") or "",
            "tournament": signal.get("tournament") or "",
            "match": (
                f"{signal.get('player_a','')} vs {signal.get('player_b','')}"
            ).strip(),
            "match_time": signal.get("match_time"),
            "outcome_player": (
                signal.get("outcome_label")
                or signal.get("target_player")
                or ""
            ),
            "entry_price": round(entry_price, 6),
            "size_usd": round(size_usd, 4),
            "shares": shares,
            "sharp_prob_at_entry": float(signal.get("sharp_prob") or 0.0),
            "divergence_at_entry": float(signal.get("divergence") or 0.0),
            "live": bool(signal.get("live", False)),
            "entry_order_id": signal.get("live_order_id") or "",
        }
        self._state["open_positions"][position_id] = position
        return position

    def _close(self, position: dict, exit_price: float, reason: str) -> dict:
        exit_price = max(0.0, min(1.0, float(exit_price)))
        shares = float(position.get("shares") or 0.0)
        entry = float(position.get("entry_price") or 0.0)
        realized = round(shares * (exit_price - entry), 4)
        closed = dict(position)
        closed.update({
            "status": "CLOSED",
            "closed_at": _now_iso(),
            "exit_price": round(exit_price, 6),
            "exit_reason": reason,
            "realized_pnl_usd": realized,
        })
        self._state["open_positions"].pop(position["id"], None)
        self._state["closed_positions"].append(closed)
        return closed

    # ------------------------------------------------------------------
    # External-trigger close (take-profit)
    # ------------------------------------------------------------------
    def take_profit(self, token_id: str, exit_price: float) -> dict | None:
        """Close the open YES position on ``token_id`` at ``exit_price``.

        Used by the strategy's take-profit gate: when the current PM price
        of a held token has run far enough above its entry price, we lock
        in the profit instead of riding the position to resolution.

        Returns the closed position dict, or ``None`` if no open position
        matches this token. Token IDs are unique per position so at most
        one match exists.
        """
        if not token_id:
            return None
        with self._lock:
            for pos in list(self._state["open_positions"].values()):
                if pos.get("token_id") != token_id:
                    continue
                closed = self._close(pos, exit_price=exit_price, reason="TAKE_PROFIT")
                self._save()
                logger.info(
                    f"[paper-book] TAKE_PROFIT {closed['outcome_player']} "
                    f"@ {closed['exit_price']:.3f} (entry {closed['entry_price']:.3f}) "
                    f"→ realized ${closed['realized_pnl_usd']:+.2f}"
                )
                return closed
            return None

    # ------------------------------------------------------------------
    # Stale-position void (safety net for unresolved markets)
    # ------------------------------------------------------------------
    def void_stale_open_positions(self, max_age_days: float) -> list[dict]:
        """Force-close open positions older than ``max_age_days`` at entry.

        Safety net for the resolution loop: tennis matches resolve within
        hours, so a position still open multiple days later means the
        underlying PM market is almost certainly settled but Gamma's
        ``closed`` field never flipped (or it flipped only after archive,
        which the resolver doesn't see). Voiding at entry yields zero
        realized PnL — conservative, but it removes the row from OPEN so
        PnL reports stop misrepresenting it as still active.
        """
        if max_age_days <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with self._lock:
            voided: list[dict] = []
            for pos in list(self._state["open_positions"].values()):
                opened_at_str = pos.get("opened_at") or ""
                if not opened_at_str:
                    continue
                try:
                    opened_at = datetime.fromisoformat(opened_at_str)
                except ValueError:
                    continue
                if opened_at.tzinfo is None:
                    opened_at = opened_at.replace(tzinfo=timezone.utc)
                if opened_at >= cutoff:
                    continue
                entry = float(pos.get("entry_price") or 0.0)
                voided.append(self._close(pos, exit_price=entry, reason="STALE_VOID"))
            if voided:
                self._save()
                for c in voided:
                    logger.info(
                        f"[paper-book] STALE_VOID {c['outcome_player']} "
                        f"opened {c['opened_at']} → closed at entry "
                        f"{c['exit_price']:.3f}"
                    )
            return voided

    # ------------------------------------------------------------------
    # External-trigger close (resolution)
    # ------------------------------------------------------------------
    def resolve(
        self,
        condition_id: str,
        winning_token_id: str | None,
    ) -> list[dict]:
        """Close all open positions on this market based on resolution.

        - winning_token_id == position.token_id  →  exit_price = 1.0 (won)
        - winning_token_id != position.token_id  →  exit_price = 0.0 (lost)
        - winning_token_id is None  →  market voided; close at entry_price
          so PnL is zero. Rare in tennis but possible (walkover before
          first ball, technical resolution, etc).

        Returns the list of newly-closed position dicts.
        """
        with self._lock:
            closed: list[dict] = []
            for pos in list(self._state["open_positions"].values()):
                if pos.get("condition_id") != condition_id:
                    continue
                if winning_token_id is None:
                    exit_price = float(pos.get("entry_price") or 0.0)
                else:
                    exit_price = 1.0 if pos.get("token_id") == winning_token_id else 0.0
                closed.append(
                    self._close(pos, exit_price, reason="RESOLVED")
                )
            if closed:
                self._save()
                for c in closed:
                    logger.info(
                        f"[paper-book] RESOLVED {c['outcome_player']} → "
                        f"exit {c['exit_price']:.2f} realized "
                        f"${c['realized_pnl_usd']:+.2f}"
                    )
            return closed

    # ------------------------------------------------------------------
    # PnL views
    # ------------------------------------------------------------------
    def realized_pnl(self) -> float:
        return round(
            sum(float(p.get("realized_pnl_usd") or 0.0)
                for p in self._state["closed_positions"]),
            4,
        )

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        """Sum of mark-to-market PnL for open positions.

        ``current_prices`` maps token_id → current YES price. Positions
        whose token_id is missing from the map contribute zero (rather
        than crash) — this lets the caller mark the book even if it
        couldn't fetch every quote.
        """
        total = 0.0
        for pos in self._state["open_positions"].values():
            cur = current_prices.get(pos.get("token_id"))
            if cur is None:
                continue
            shares = float(pos.get("shares") or 0.0)
            entry = float(pos.get("entry_price") or 0.0)
            total += shares * (float(cur) - entry)
        return round(total, 4)

    def open_position_count(self) -> int:
        return len(self._state["open_positions"])

    def open_position_condition_ids(self) -> set[str]:
        return {
            pos["condition_id"]
            for pos in self._state["open_positions"].values()
            if pos.get("condition_id")
        }

    def open_positions(self) -> list[dict]:
        return list(self._state["open_positions"].values())

    def closed_positions(self) -> list[dict]:
        return list(self._state["closed_positions"])

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def breakdown_by_event(
        self,
        current_prices: dict[str, float] | None = None,
    ) -> list[dict]:
        """Per-event PnL breakdown.

        Each entry::

            {"event_title": "...",
             "realized_pnl_usd": 1.23,
             "unrealized_pnl_usd": -0.45,
             "total_pnl_usd": 0.78,
             "open_positions": [...],
             "closed_positions": [...]}

        Sorted by total_pnl_usd descending so winners surface first.
        """
        current_prices = current_prices or {}
        groups: "OrderedDict[str, dict]" = OrderedDict()

        def _bucket(ev: str) -> dict:
            if ev not in groups:
                groups[ev] = {
                    "event_title": ev,
                    "realized_pnl_usd": 0.0,
                    "unrealized_pnl_usd": 0.0,
                    "open_positions": [],
                    "closed_positions": [],
                }
            return groups[ev]

        for pos in self._state["closed_positions"]:
            g = _bucket(pos.get("event_title") or "(unknown event)")
            g["realized_pnl_usd"] += float(pos.get("realized_pnl_usd") or 0.0)
            g["closed_positions"].append(pos)

        for pos in self._state["open_positions"].values():
            g = _bucket(pos.get("event_title") or "(unknown event)")
            cur = current_prices.get(pos.get("token_id"))
            if cur is not None:
                shares = float(pos.get("shares") or 0.0)
                entry = float(pos.get("entry_price") or 0.0)
                g["unrealized_pnl_usd"] += shares * (float(cur) - entry)
            g["open_positions"].append(pos)

        for g in groups.values():
            g["realized_pnl_usd"] = round(g["realized_pnl_usd"], 4)
            g["unrealized_pnl_usd"] = round(g["unrealized_pnl_usd"], 4)
            g["total_pnl_usd"] = round(
                g["realized_pnl_usd"] + g["unrealized_pnl_usd"], 4
            )

        return sorted(
            groups.values(),
            key=lambda g: g["total_pnl_usd"],
            reverse=True,
        )
