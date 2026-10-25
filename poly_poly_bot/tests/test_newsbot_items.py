"""newsbot.items: the Item schema, the dedup store, the shared parsers.
Every timestamp here is pinned; nothing reads the wall clock."""
from __future__ import annotations

import json

import pytest

from src.newsbot import items
from src.newsbot.items import DedupStore, Item, parse_iso8601, parse_rfc822, parse_timestamp, strip_html

T0 = 1792922000.0  # 2026-10-25T09:53:20Z, inside the probe window


def _item(i: int = 1) -> Item:
    return Item(id=f"rss:x:{i}", source="rss:x", domains=("geo", "corp"), published_ts=T0 - 60, seen_ts=T0,
                title=f"t{i}", text="body", url="https://example.com/1")


def test_item_round_trips_through_dict_with_domains_as_a_tuple():
    it = _item()
    d = it.to_dict()
    assert d["domains"] == ["geo", "corp"]      # JSON-friendly on the way out
    back = Item.from_dict(json.loads(json.dumps(d)))
    assert back == it and isinstance(back.domains, tuple)


def test_item_is_frozen_and_id_is_source_colon_native():
    it = _item()
    with pytest.raises(Exception):
        it.title = "x"  # type: ignore[misc]
    assert items.make_id("tg:financialjuice", "142489") == "tg:financialjuice:142489"


# --- dedup store -----------------------------------------------------------

def test_dedup_add_is_idempotent_and_seen_reads_it_back(tmp_path):
    d = DedupStore(tmp_path / "seen.json")
    assert d.add("a") is True
    assert d.add("a") is False
    assert d.seen("a") and not d.seen("b") and "a" in d and len(d) == 1


def test_dedup_persists_atomically_and_reloads(tmp_path):
    p = tmp_path / "news" / "seen.json"
    d = DedupStore(p)
    d.add("a")
    d.add("b")
    assert d.save() is True
    assert d.save() is False, "nothing dirty, nothing written"
    assert not list(p.parent.glob("*.tmp")), "no temp file left behind"
    assert json.loads(p.read_text())["ids"] == ["a", "b"]
    again = DedupStore(p)
    assert again.seen("a") and again.seen("b") and len(again) == 2


def test_dedup_cap_evicts_oldest_first(tmp_path):
    d = DedupStore(tmp_path / "seen.json", cap=3)
    for i in range(5):
        d.add(str(i))
    assert len(d) == 3
    assert not d.seen("0") and not d.seen("1")
    assert d.seen("2") and d.seen("4")
    d.save()
    assert json.loads((tmp_path / "seen.json").read_text())["ids"] == ["2", "3", "4"]


def test_dedup_default_cap_is_50k_and_a_torn_file_starts_empty(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text("{not json")
    d = DedupStore(p)
    assert len(d) == 0 and d.cap == 50_000


def test_dedup_load_honours_cap_on_an_oversized_file(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({"ids": [str(i) for i in range(10)]}))
    d = DedupStore(p, cap=4)
    assert len(d) == 4 and d.seen("9") and not d.seen("5"), "the newest survive, the file's tail"


# --- timestamps ------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    ("Sun, 25 Oct 2026 06:02:05 +0000", 1792908125.0),      # trumpstruth
    ("Sun, 25 Oct 2026 05:00:28 -0400", 1792918828.0),      # Fox, offset
    ("Sun, 25 Oct 2026 08:56 GMT", 1792918560.0),           # CNBC, no seconds
    ("Sat, 25 Oct 2026 10:00:00 EST", 1792940400.0),        # ESPN-style zone name = -0500
    ("Sun, 25 Oct 2026 09:03:21 +0000", 1792919001.0),      # NYT
])
def test_rfc822_with_zones(s, expected):
    assert parse_rfc822(s) == expected
    assert parse_timestamp(s) == expected


@pytest.mark.parametrize("s,expected", [
    ("2026-10-23T17:30:15-04:00", 1792791015.0),            # SEC <updated>
    ("2026-10-24T12:43:29+00:00", 1792845809.0),            # Telegram <time datetime>
    ("2026-10-25T09:36:28.172Z", 1792920988.172),           # Bluesky createdAt
    ("2026-10-25T09:56:49Z", 1792922209.0),                 # HN created_at
    ("2026-10-25T09:34:00Z", 1792920840.0),                 # DW dc:date
    ("2026-10-25T09:34:00", 1792920840.0),                  # naive = UTC
])
def test_iso8601_with_offsets(s, expected):
    assert parse_iso8601(s) == pytest.approx(expected, abs=1e-6)
    assert parse_timestamp(s) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("s", ["", None, "yesterday", "25/10/2026"])
def test_unparseable_timestamps_are_none_not_zero(s):
    assert parse_timestamp(s) is None


# --- html ------------------------------------------------------------------

def test_strip_html_keeps_link_urls_when_asked():
    frag = 'Zelenskiy: <b>restrictions</b> removed<br>see <a href="https://x.com/a/status/1">x.com/a/stat…</a> and <a href="https://e.com/p">here</a>'
    assert strip_html(frag) == "Zelenskiy: restrictions removed\nsee x.com/a/stat… and here"
    kept = strip_html(frag, keep_links=True)
    assert "https://x.com/a/status/1" in kept, "a truncated visible URL is replaced by the real href"
    assert "here (https://e.com/p)" in kept


def test_strip_html_unescapes_and_collapses_whitespace():
    assert strip_html("<p>A &amp; B</p>\n\n\n<p>  C   D </p>") == "A & B\nC D"
    assert strip_html(None) == "" and strip_html("") == ""
    assert items.first_line("\n\n  headline here\nmore") == "headline here"
    assert items.first_line("x" * 300).endswith("…") and len(items.first_line("x" * 300)) == 200
