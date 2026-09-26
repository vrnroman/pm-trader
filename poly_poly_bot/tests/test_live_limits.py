"""Live limits (s-qbzbrw): the analyst moves a number only inside its band,
only down for money, only for a day; the owner's number is the ruling."""
from __future__ import annotations

import pytest

from src.config import CONFIG
from src.copy_trading import live_limits as ll

NOW = 1_789_700_000.0


@pytest.fixture
def limits_env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ll.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setenv("LIVE_MAX_PER_WALLET_DAY", "3")
    monkeypatch.setenv("FETCH_INTERVAL", "3")
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 3)
    monkeypatch.setattr(CONFIG, "fetch_interval", 3.0)
    return tmp_path


def test_the_owners_number_is_the_config_then_the_env_then_the_default(limits_env, monkeypatch):
    assert ll.owner_value("LIVE_MAX_PER_WALLET_DAY") == 3
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 2)
    assert ll.owner_value("LIVE_MAX_PER_WALLET_DAY") == 2, "the validated config is what the bot runs on"
    # a parameter that lives only as a module constant: env, then the default
    monkeypatch.setenv("FORM_DAYS", "10")
    assert ll.owner_value("FORM_DAYS") == 10.0
    monkeypatch.delenv("FORM_DAYS")
    assert ll.owner_value("FORM_DAYS") == 14.0, "the table default is the shipped value"
    monkeypatch.setenv("FORM_DAYS", "garbage")
    assert ll.owner_value("FORM_DAYS") == 14.0
    assert ll.owner_value("NOT_A_PARAM") is None


def test_money_moves_down_only_inside_the_band_and_expires(limits_env):
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", 2, why="fewer copies while form is thin", now=NOW)
    assert ok and ll.current("LIVE_MAX_PER_WALLET_DAY", NOW + 60) == 2
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW + ll.ANALYST_TTL_S) == 3, "snaps back to the owner"
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", 21, why="more", now=NOW)
    assert not ok and "outside the band" in why, "the band tops out at the owner's 20 (2026-09-26)"
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", 4, why="more", now=NOW)
    assert not ok and "exceeds the owner's 3" in why
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", 3, why="same", now=NOW)
    assert ok, "equal to the owner's is allowed"
    ok, why = ll.propose("LIVE_BUDGET_PER_COPY_FRAC", 0.05, why="less", now=NOW)
    assert not ok and "not a parameter" in why, "the stake fraction is not the analyst's to move"
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", "two", why="x", now=NOW)
    assert not ok and "not a int" in why


def test_money_never_exceeds_the_owner_even_inside_the_band(limits_env, monkeypatch):
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 2)
    ok, why = ll.propose("LIVE_MAX_PER_WALLET_DAY", 3, why="x", now=NOW)
    assert not ok and "exceeds the owner's 2" in why
    # a value that was fine becomes owner-capped when the owner lowers his number
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 3)
    assert ll.propose("LIVE_MAX_PER_WALLET_DAY", 3, why="x", now=NOW)[0]
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 1)
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW + 1) == 1, "the owner's newer, lower number wins"


def test_timing_moves_either_way_inside_the_band(limits_env):
    assert ll.propose("FETCH_INTERVAL", 5, why="less api load", now=NOW)[0]
    assert ll.current("FETCH_INTERVAL", NOW + 1) == 5.0
    assert ll.propose("FETCH_INTERVAL", 2, why="faster", now=NOW)[0]
    assert ll.current("FETCH_INTERVAL", NOW + 1) == 2.0
    assert not ll.propose("FETCH_INTERVAL", 9, why="x", now=NOW)[0]


def test_unknown_parameters_and_bad_files_fall_back_to_the_owner(limits_env):
    assert not ll.propose("LIVE_BUDGET_USD", 10, why="x", now=NOW)[0], "exposure is owner-only forever"
    assert ll.current("LIVE_BUDGET_USD", NOW) is None
    (limits_env / ll.FILE).write_text("{not json")
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW) == 3
    (limits_env / ll.FILE).write_text('{"LIVE_MAX_PER_WALLET_DAY": {"analyst_value": "x", "expires_at": 9e12}}')
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW) == 3
    (limits_env / ll.FILE).write_text('{"LIVE_MAX_PER_WALLET_DAY": {"analyst_value": 9, "expires_at": 9e12}}')
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW) == 3, "a hand-edited out-of-band value is ignored"


def test_lines_show_the_owner_and_any_analyst_value_in_force(limits_env):
    ll.propose("LIVE_MAX_PER_WALLET_DAY", 1, why="thin form", now=NOW)
    out = ll.lines(NOW + 3600)
    assert any(l.startswith("LIVE_MAX_PER_WALLET_DAY: 1 (analyst, 23.0 h left, owner 3): thin form") for l in out)
    assert any(l.startswith("FETCH_INTERVAL: 3.0 (owner) band 2..5") for l in out)
    assert all("—" not in l for l in out)
    assert ll.clear("LIVE_MAX_PER_WALLET_DAY") and ll.current("LIVE_MAX_PER_WALLET_DAY", NOW + 1) == 3
    assert ll.clear("LIVE_MAX_PER_WALLET_DAY") is False


# --------------------------------------------------------------------------- #
# The call sites: the consumers read current(), the owner's number falls back
# --------------------------------------------------------------------------- #

def test_the_per_wallet_cap_reads_the_live_limit(limits_env, monkeypatch):
    from src.copy_trading import daily_spend_guard as dsg
    import inspect
    src = inspect.getsource(dsg)
    assert 'live_limits.current("LIVE_MAX_PER_WALLET_DAY")' in src
    ll.propose("LIVE_MAX_PER_WALLET_DAY", 1, why="x", now=NOW)
    assert ll.current("LIVE_MAX_PER_WALLET_DAY", NOW + 1) == 1


def test_the_other_consumers_read_current_too():
    import inspect
    from src.copy_trading import data_api_source, ops_watch, wallet_form
    assert 'live_limits.current("FETCH_INTERVAL")' in inspect.getsource(data_api_source)
    assert 'live_limits.current("OPS_REARM_CLEAR_S")' in inspect.getsource(ops_watch.maybe_rearm)
    assert 'live_limits.current("OPS_REARM_MAX_PER_DAY")' in inspect.getsource(ops_watch.maybe_rearm)
    assert 'live_limits.current("FORM_DAYS", now)' in inspect.getsource(wallet_form.scan)


def test_a_shorter_form_window_is_used_by_the_scan(limits_env, monkeypatch, tmp_path):
    """The analyst shortens FORM_DAYS to 7 for a day: the scan measures 7 days
    and the record says so."""
    from src.copy_trading import wallet_form as wf, ops_watch, zset
    monkeypatch.setattr(wf.CONFIG, "data_dir", str(limits_env))
    monkeypatch.setattr(ops_watch.CONFIG, "data_dir", str(limits_env))
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    ll.propose("FORM_DAYS", 7, why="recent form only", now=NOW)
    seen = {}
    def get(url):
        return []
    real_compute = wf.compute
    def spy(w, acts, pos, **kw):
        seen["days"] = kw.get("days")
        return real_compute(w, acts, pos, **kw)
    monkeypatch.setattr(wf, "compute", spy)
    wf.scan(get=get, send=None, now=NOW + 1, wallets=["0xa"])
    assert seen["days"] == 7.0
