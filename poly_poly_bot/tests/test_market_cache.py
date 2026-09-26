"""The on-chain market lookup: a token resolves to a NAMED market, or to nothing.

Regression for 2026-09-26: the CLOB ``/markets?asset_id=`` call ignored its
filter and returned a paginated envelope; the code cached an empty title for
every token and the phone read ``BUY $6.40 on ""``.
"""

from __future__ import annotations

import json

import pytest

from src.copy_trading import market_cache as mc
from src.models import MarketMeta

TOKEN_YES = "6295826542822962219075765493603047858704411257953473473091861902403059749821"
TOKEN_NO = "41559178175691547751417001527831534132330818263699898215827815896930306247487"

GAMMA_ROW = {
    "question": "Solihull Moors FC to score first vs. Boreham Wood FC?",
    "conditionId": "0x08459f73123e5ec0fa6776c7aaf12247c3a8d204c1939fae34619d4d6d21a711",
    "outcomes": json.dumps(["Yes", "No"]),
    "clobTokenIds": json.dumps([TOKEN_YES, TOKEN_NO]),
}

# What the old CLOB call actually answered: the first page of every market.
CLOB_ENVELOPE = {
    "data": [{"question": "Will Benjamin Netanyahu remain prime minister?",
              "condition_id": "0xabc", "tokens": [{"token_id": "1", "outcome": "Yes"}]}],
    "next_cursor": "MTAw", "limit": 100, "count": 100,
}


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_CACHE_PATH", tmp_path / "market-cache.json")
    monkeypatch.setattr(mc, "_cache", {})
    monkeypatch.setattr(mc, "_negative", {})
    monkeypatch.setattr(mc, "_loaded", False)


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _stub_gamma(monkeypatch, answers: dict[str, object], calls: list):
    """``answers`` maps ``closed`` param ("" or "true") to a payload."""
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            calls.append((url, dict(params or {})))
            assert url.startswith(mc.GAMMA_API_URL), "the lookup must go to Gamma, not the CLOB"
            assert "clob_token_ids" in params, "the lookup must filter by token"
            return _Resp(answers.get(params.get("closed", ""), []))
    monkeypatch.setattr(mc.httpx, "Client", _Client)


def test_gamma_row_names_the_market_and_the_tokens_outcome():
    meta = mc.meta_from_rows([GAMMA_ROW], TOKEN_NO)
    assert meta == MarketMeta(
        condition_id=GAMMA_ROW["conditionId"],
        market="Solihull Moors FC to score first vs. Boreham Wood FC?",
        outcome="No",
        token_id=TOKEN_NO,
    )
    assert mc.meta_from_rows([GAMMA_ROW], TOKEN_YES).outcome == "Yes"


def test_the_clob_envelope_is_not_a_market():
    # The regression: the old code read this dict as a market with no title
    # and cached ``market=""``.
    assert mc.meta_from_rows(mc._rows(CLOB_ENVELOPE), TOKEN_NO) is None
    # ...and a page of other people's markets (Gamma-shaped rows that list
    # tokens, none of them ours) is not ours either.
    other = dict(GAMMA_ROW, clobTokenIds=json.dumps(["1", "2"]))
    assert mc.meta_from_rows([other], TOKEN_NO) is None
    # A bare envelope with no rows, and a row with no title, resolve to nothing.
    assert mc.meta_from_rows([], TOKEN_NO) is None
    assert mc.meta_from_rows([{"conditionId": "0x1", "question": "  "}], TOKEN_NO) is None


def test_resolved_token_is_cached_to_disk_with_its_title(monkeypatch):
    calls: list = []
    _stub_gamma(monkeypatch, {"": [GAMMA_ROW]}, calls)
    meta = mc.get_market_meta(TOKEN_NO)
    assert meta is not None and meta.market.startswith("Solihull") and meta.outcome == "No"
    on_disk = json.loads(mc._CACHE_PATH.read_text())
    assert on_disk[TOKEN_NO]["market"].startswith("Solihull")
    # second call served from memory, no further request
    n = len(calls)
    assert mc.get_market_meta(TOKEN_NO) == meta
    assert len(calls) == n


def test_closed_market_is_found_on_the_closed_variant(monkeypatch):
    calls: list = []
    _stub_gamma(monkeypatch, {"": [], "true": [GAMMA_ROW]}, calls)
    meta = mc.get_market_meta(TOKEN_YES)
    assert meta is not None and meta.outcome == "Yes"
    assert [c[1].get("closed", "") for c in calls] == ["", "true"]


def test_unnamed_token_is_never_written_to_disk_and_not_re_asked_within_ttl(monkeypatch):
    calls: list = []
    _stub_gamma(monkeypatch, {"": [], "true": []}, calls)
    assert mc.get_market_meta(TOKEN_NO) is None
    assert not mc._CACHE_PATH.exists() or TOKEN_NO not in json.loads(mc._CACHE_PATH.read_text())
    n = len(calls)
    assert mc.get_market_meta(TOKEN_NO) is None
    assert len(calls) == n, "a fresh miss is remembered in memory, Gamma is not hammered per poll"
    # ...but only for the TTL: once it lapses the token is asked again
    mc._negative[TOKEN_NO] -= mc.NEGATIVE_TTL_S + 1
    _stub_gamma(monkeypatch, {"": [GAMMA_ROW]}, calls)
    assert mc.get_market_meta(TOKEN_NO).market.startswith("Solihull")


def test_poisoned_untitled_rows_are_dropped_on_load_and_re_resolved(monkeypatch):
    # The VM's cache had 1008 of these on 2026-09-26.
    mc._CACHE_PATH.write_text(json.dumps({
        TOKEN_NO: {"condition_id": "", "market": "", "outcome": "", "token_id": TOKEN_NO},
        "77": {"condition_id": "0x77", "market": "Kept", "outcome": "Yes", "token_id": "77"},
    }))
    calls: list = []
    _stub_gamma(monkeypatch, {"": [GAMMA_ROW]}, calls)
    assert mc.get_market_meta("77").market == "Kept"
    assert calls == [], "a titled row is served from disk"
    assert mc.get_market_meta(TOKEN_NO).market.startswith("Solihull")
    on_disk = json.loads(mc._CACHE_PATH.read_text())
    assert on_disk[TOKEN_NO]["market"].startswith("Solihull")
    assert on_disk["77"]["market"] == "Kept"


@pytest.mark.asyncio
async def test_warm_cache_uses_gamma_and_skips_untitled(monkeypatch):
    calls: list = []

    class _AClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            calls.append(dict(params or {}))
            assert url.startswith(mc.GAMMA_API_URL)
            if params["clob_token_ids"] == TOKEN_YES and not params.get("closed"):
                return _Resp([GAMMA_ROW])
            return _Resp([])
    monkeypatch.setattr(mc.httpx, "AsyncClient", _AClient)

    await mc.warm_cache([TOKEN_YES, TOKEN_NO, TOKEN_YES])
    assert mc._cache[TOKEN_YES].outcome == "Yes"
    assert TOKEN_NO not in mc._cache
    assert TOKEN_NO in mc._negative
    on_disk = json.loads(mc._CACHE_PATH.read_text())
    assert set(on_disk) == {TOKEN_YES}


def test_phone_label_names_the_bet_or_says_it_is_unnamed():
    from src.copy_trading.telegram_notifier import _bet_label
    assert _bet_label("Hangzhou Open: Coleman Wong vs Adolfo Vallejo", "Coleman Wong") == \
        '"Hangzhou Open: Coleman Wong vs Adolfo Vallejo" — Coleman Wong'
    assert _bet_label("Map Handicap: HERO (-1.5)", "") == '"Map Handicap: HERO (-1.5)"'
    assert _bet_label("", "") == "(market unnamed)"
    assert "&lt;b&gt;" in _bet_label("<b>x</b>", "")
