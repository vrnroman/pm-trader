"""Persistent runtime toggles, file-backed.

Each strategy has a preview/live flag. Default on first read = the global
``PREVIEW_MODE`` env flag (via ``CONFIG.preview_mode``). Subsequent flips
made through Telegram are persisted to ``<data_dir>/runtime_state.json``
so the chosen mode survives container restarts.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from src.config import CONFIG

_lock = threading.Lock()
_state: dict[str, Any] | None = None


def _path() -> str:
    return os.path.join(CONFIG.data_dir or ".", "runtime_state.json")


def _load_locked() -> dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    p = _path()
    loaded: dict[str, Any] = {}
    if os.path.exists(p):
        try:
            with open(p) as f:
                loaded = json.load(f) or {}
        except Exception:
            loaded = {}
    loaded.setdefault("preview", {})
    for s in (1, 2, 3):
        loaded["preview"].setdefault(str(s), bool(CONFIG.preview_mode))
    _state = loaded
    return _state


def _save_locked() -> None:
    p = _path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_state, f, indent=2)
    os.replace(tmp, p)


def is_preview(strategy: int) -> bool:
    with _lock:
        st = _load_locked()
        return bool(st["preview"].get(str(strategy), CONFIG.preview_mode))


def set_preview(strategy: int, value: bool) -> None:
    with _lock:
        st = _load_locked()
        st["preview"][str(strategy)] = bool(value)
        _save_locked()


def all_modes() -> dict[int, bool]:
    with _lock:
        st = _load_locked()
        return {int(k): bool(v) for k, v in st["preview"].items()}
