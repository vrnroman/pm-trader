"""Book B's recipe in one place (s-ye5990): main.py spreads it, the
experiment process runs it as the control, cards may override only KNOBS."""
from __future__ import annotations

import pathlib
import re

from src.config import CONFIG
from src.copy_trading import book_recipes

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_main_builds_book_b_from_the_recipe_and_nowhere_else():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    b = src[src.index("def _copy_paper_b_loop"):src.index("def _ab_race_reporter_loop")]
    assert "book_recipes.book_b_kwargs(CONFIG)" in b
    for needle in ("min_usd=CONFIG.copy_paper_min_usd", "fill_at_their_price_bps=CONFIG.copy_paper_b_slippage_bps",
                   'strategy="B"'):
        assert needle not in b, f"{needle} must come from the recipe, not main.py"
    # the callables stay with the process
    assert "blacklist_provider=lambda: promotion_state.active_blacklist(scope=_scope)" in b
    assert "detector_factory=detector_factory" in b and "observer=_get_shadow_observer()" in b


def test_the_recipe_is_book_b(monkeypatch):
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    monkeypatch.setattr(CONFIG, "copy_paper_b_slippage_bps", 100)
    monkeypatch.setattr(CONFIG, "copy_paper_b_max_per_wallet_day", 25)
    monkeypatch.setattr(CONFIG, "copy_paper_b_max_per_category_day", 0)
    k = book_recipes.book_b_kwargs(CONFIG)
    assert k["strategy"] == "B" and k["fill_gate_bps"] is None and k["fill_at_their_price_bps"] == 100
    assert k["min_usd"] == 300.0 and k["max_copies_per_wallet_day"] == 25
    assert k["max_copies_per_category_day"] is None, "a cap of 0 is off"
    assert k["ledger_path"] == CONFIG.copy_paper_b_ledger
    assert k["gate_history_path"].endswith("gate-history.jsonl")
    assert k["relief_evidence_n"] is None and k["relief_max_per_category_day"] is None


def test_knobs_are_typed_and_unknown_names_refuse_the_whole_card():
    ok, why = book_recipes.coerce_knobs({"min_usd": "150", "first_entry_only": "false", "max_copies_per_wallet_day": 3})
    assert why == "" and ok == {"min_usd": 150.0, "first_entry_only": False, "max_copies_per_wallet_day": 3}
    assert book_recipes.coerce_knobs({"ledger_path": "/etc/passwd"}) == ({}, "ledger_path is not a knob an experiment may change")
    assert book_recipes.coerce_knobs({"min_usd": "cheap"})[1].startswith("min_usd:")
    assert set(book_recipes.KNOBS) >= set(book_recipes.KNOB_ENV), "every env-backed knob is a knob"


def test_every_knob_env_name_exists_in_config():
    src = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
    for env in book_recipes.KNOB_ENV.values():
        assert re.search(rf'"{env}"', src), f"{env} is not a config env name"


def test_a_cap_of_zero_is_not_a_knob_and_strings_are_read_as_booleans():
    ok, why = book_recipes.coerce_knobs({"max_copies_per_wallet_day": 0})
    assert ok == {} and "caps on a card are 1 or more" in why
    assert book_recipes.as_bool("false") is False and book_recipes.as_bool("True") is True and book_recipes.as_bool(0) is False
