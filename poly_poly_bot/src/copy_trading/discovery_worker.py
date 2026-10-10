"""Run the discovery sweep (``evaluate_sweep``) in a child process.

Why (2026-10-10 memory RCA): a sweep peaks near 1.1GB — price series held as
millions of small tuples, ~100 parsed /activity files per chunk, ~150k market
resolutions. Python frees those objects when the sweep returns, but the memory
stays with the process: pymalloc only returns a 1MB arena when EVERY object in
it is dead, and the sweep's long-lived survivors (pool, results, other threads'
objects) pin almost all of them. ``malloc_trim`` cannot touch pymalloc arenas.
So the trading process sat at the sweep's high-water mark for good (760MB RSS
+ 380MB swap, five hours after a sweep had finished) on a 2GB VM that had
already hung once from memory exhaustion.

A child process gives the whole sweep heap back to the OS when it exits. The
parent sends the inputs and reads back the ``wallet -> Eval`` map (a few
hundred small frozen dataclasses) through pickle files; everything else the
sweep produces lives on disk already (wcache, rescache).

``evaluate_in_subprocess`` has exactly ``evaluate_sweep``'s signature, so the
runner swaps one for the other. ``DISCOVERY_SUBPROCESS=0`` runs the sweep
in-process again (the old behaviour) without a deploy of new code.
"""

from __future__ import annotations

import logging
import os
import pickle
import resource
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional

logger = logging.getLogger("poly_poly_bot")

# On shutdown the child gets SIGTERM, which sets the sweep's stop event: it
# finishes the wallet in hand and returns what it has (the in-process sweep did
# the same). After this many seconds it is killed and the sweep counts as empty.
STOP_GRACE_S = 8.0
_POLL_S = 1.0
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def enabled() -> bool:
    return os.environ.get("DISCOVERY_SUBPROCESS", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return -1.0


def _maxrss_mb(who: int) -> float:
    r = resource.getrusage(who).ru_maxrss
    # Linux reports KiB, macOS bytes.
    return r / (1024.0 * 1024.0) if sys.platform == "darwin" else r / 1024.0


def evaluate_in_subprocess(
    cfg,
    *,
    must_include: Optional[set] = None,
    cache_dir: Optional[str] = None,
    activity_ttl_s: float = 86400.0,
    stop: Optional[threading.Event] = None,
    prior_copy_stats: Optional[dict] = None,
    _argv: Optional[list] = None,
) -> dict:
    """``evaluate_sweep`` in a child process. Returns {} if the child fails.

    A failed child is logged as a WARNING and yields {}, the same as an empty
    or stopped sweep: the runner then writes nothing and keeps the previous
    watchlist, which is the safe direction.
    """
    if not enabled():
        from src.copy_trading.discovery_data import evaluate_sweep
        return evaluate_sweep(
            cfg, must_include=must_include, cache_dir=cache_dir,
            activity_ttl_s=activity_ttl_s, stop=stop,
            prior_copy_stats=prior_copy_stats)

    if stop is not None and stop.is_set():
        return {}
    work = tempfile.mkdtemp(prefix="discovery-")
    in_path = os.path.join(work, "in.pkl")
    out_path = os.path.join(work, "out.pkl")
    try:
        with open(in_path, "wb") as f:
            pickle.dump({
                "cfg": cfg, "must_include": set(must_include or ()),
                "cache_dir": cache_dir, "activity_ttl_s": activity_ttl_s,
                "prior_copy_stats": prior_copy_stats,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        argv = _argv or [sys.executable, "-m", "src.copy_trading.discovery_worker"]
        t0 = time.time()
        # The child imports `src.…` whatever its cwd: put the project root first
        # on its path (cwd itself is inherited, so relative data paths match).
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (_PROJECT_ROOT, env.get("PYTHONPATH")) if p)
        proc = subprocess.Popen(argv + [in_path, out_path], env=env)
        logger.info("[DISCOVERY] sweep started in child process pid=%d", proc.pid)
        stopped_at: Optional[float] = None
        while True:
            try:
                rc = proc.wait(timeout=_POLL_S)
                break
            except subprocess.TimeoutExpired:
                pass
            if stop is not None and stop.is_set():
                if stopped_at is None:
                    stopped_at = time.time()
                    proc.terminate()
                elif time.time() - stopped_at > STOP_GRACE_S:
                    proc.kill()
        if rc != 0:
            if stopped_at is not None:
                logger.info("[DISCOVERY] sweep child stopped for shutdown (rc=%s)", rc)
            else:
                logger.warning("[DISCOVERY] sweep child exited rc=%s — no "
                               "evaluations this sweep, watchlist kept", rc)
            return {}
        try:
            with open(out_path, "rb") as f:
                evaluated = pickle.load(f)
        except (OSError, EOFError, pickle.UnpicklingError):
            logger.warning("[DISCOVERY] sweep child left no readable result — "
                           "no evaluations this sweep, watchlist kept",
                           exc_info=True)
            return {}
        logger.info(
            "[DISCOVERY] sweep child done in %.0fs: %d evaluated, child peak "
            "RSS %.0fMB, bot RSS now %.0fMB", time.time() - t0, len(evaluated),
            _maxrss_mb(resource.RUSAGE_CHILDREN), _rss_mb())
        return evaluated
    except Exception:
        logger.warning("[DISCOVERY] could not run the sweep child", exc_info=True)
        return {}
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(work)
        except OSError:
            pass


def _child_main(in_path: str, out_path: str) -> int:
    import src.logger  # noqa: F401 — configures the "poly_poly_bot" handlers
    from src.copy_trading.discovery_data import evaluate_sweep

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    with open(in_path, "rb") as f:
        args = pickle.load(f)
    evaluated = evaluate_sweep(
        args["cfg"], must_include=args["must_include"],
        cache_dir=args["cache_dir"], activity_ttl_s=args["activity_ttl_s"],
        stop=stop, prior_copy_stats=args["prior_copy_stats"])
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(evaluated, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(_child_main(sys.argv[1], sys.argv[2]))
