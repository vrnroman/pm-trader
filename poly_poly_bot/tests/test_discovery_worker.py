"""The discovery sweep runs in a child process (2026-10-10 memory RCA)."""

import pickle
import sys
import threading
import time

from src.copy_trading import discovery_worker as dw
from src.copy_trading.discovery import DiscoveryConfig, Eval


def _fake_child(tmp_path, body: str) -> list:
    """A stand-in child: argv[1] = input pickle, argv[2] = output pickle."""
    script = tmp_path / "child.py"
    script.write_text(
        "import pickle, sys, time, signal\n"
        "inp, out = sys.argv[1], sys.argv[2]\n"
        "args = pickle.load(open(inp, 'rb'))\n" + body)
    return [sys.executable, str(script)]


def test_result_comes_back_from_the_child(tmp_path):
    argv = _fake_child(tmp_path, (
        "from src.copy_trading.discovery import Eval\n"
        "res = {w: Eval(wallet=w, copy_n=7) for w in sorted(args['must_include'])}\n"
        "res['_ttl'] = args['activity_ttl_s']\n"
        "pickle.dump(res, open(out, 'wb'))\n"))
    out = dw.evaluate_in_subprocess(
        DiscoveryConfig(), must_include={"0xa", "0xb"}, activity_ttl_s=123.0,
        prior_copy_stats={"0xa": {"copy_n": 3}}, _argv=argv)
    assert out["0xa"] == Eval(wallet="0xa", copy_n=7)
    assert set(out) == {"0xa", "0xb", "_ttl"} and out["_ttl"] == 123.0


def test_a_crashed_child_yields_no_evaluations(tmp_path, caplog):
    argv = _fake_child(tmp_path, "raise SystemExit(3)\n")
    assert dw.evaluate_in_subprocess(DiscoveryConfig(), _argv=argv) == {}
    assert "rc=3" in caplog.text


def test_a_child_without_a_result_yields_no_evaluations(tmp_path):
    argv = _fake_child(tmp_path, "pass\n")
    assert dw.evaluate_in_subprocess(DiscoveryConfig(), _argv=argv) == {}


def test_shutdown_stops_the_child(tmp_path, monkeypatch):
    monkeypatch.setattr(dw, "_POLL_S", 0.05)
    monkeypatch.setattr(dw, "STOP_GRACE_S", 0.5)
    # Ignores SIGTERM, so only the kill after the grace window ends it.
    argv = _fake_child(tmp_path, (
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(60)\n"))
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    t0 = time.time()
    assert dw.evaluate_in_subprocess(DiscoveryConfig(), stop=stop, _argv=argv) == {}
    assert time.time() - t0 < 10


def test_already_stopped_never_starts_a_child(tmp_path):
    stop = threading.Event()
    stop.set()
    argv = _fake_child(tmp_path, "raise SystemExit(9)\n")
    assert dw.evaluate_in_subprocess(DiscoveryConfig(), stop=stop, _argv=argv) == {}


def test_switch_off_runs_the_sweep_in_process(monkeypatch):
    from src.copy_trading import discovery_data
    seen = {}

    def fake(cfg, **kw):
        seen.update(kw)
        return {"0xa": Eval(wallet="0xa")}

    monkeypatch.setenv("DISCOVERY_SUBPROCESS", "0")
    monkeypatch.setattr(discovery_data, "evaluate_sweep", fake)
    out = dw.evaluate_in_subprocess(DiscoveryConfig(), must_include={"0xa"})
    assert out == {"0xa": Eval(wallet="0xa")}
    assert seen["must_include"] == {"0xa"}


def test_child_main_runs_the_real_entry_contract(tmp_path, monkeypatch):
    """The child's own side: reads the inputs, passes them to evaluate_sweep
    with a stop event, writes the result atomically."""
    from src.copy_trading import discovery_data
    seen = {}

    def fake(cfg, **kw):
        seen.update(kw, cfg=cfg)
        return {"0xa": Eval(wallet="0xa", capture_cents=2.5)}

    monkeypatch.setattr(discovery_data, "evaluate_sweep", fake)
    monkeypatch.setattr(dw.signal, "signal", lambda *a: None)
    cfg = DiscoveryConfig(min_usd=150.0)
    inp, out = tmp_path / "in.pkl", tmp_path / "out.pkl"
    inp.write_bytes(pickle.dumps({
        "cfg": cfg, "must_include": {"0xa"}, "cache_dir": "/c",
        "activity_ttl_s": 5.0, "prior_copy_stats": {}}))
    assert dw._child_main(str(inp), str(out)) == 0
    assert pickle.loads(out.read_bytes()) == {"0xa": Eval(wallet="0xa", capture_cents=2.5)}
    assert seen["cfg"] == cfg and seen["cache_dir"] == "/c"
    assert isinstance(seen["stop"], threading.Event)
    assert not (tmp_path / "out.pkl.tmp").exists()


def test_the_real_module_starts_as_a_child(tmp_path):
    """`python -m src.copy_trading.discovery_worker` imports and runs: a bad
    input path must fail inside the child (nonzero rc), not at import."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "src.copy_trading.discovery_worker",
         str(tmp_path / "missing.pkl"), str(tmp_path / "out.pkl")],
        capture_output=True, text=True, timeout=120)
    assert r.returncode != 0
    assert "missing.pkl" in r.stderr
