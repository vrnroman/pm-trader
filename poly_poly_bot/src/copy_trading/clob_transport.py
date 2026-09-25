"""A dropped CLOB connection is replaced and the request sent again, once.

2026-09-25: four live BUYs and a run of order-book reads failed with
"Request exception!" in a day. Each was the first CLOB call after a quiet
stretch, and each logged "Server disconnected" from httpx.
``py_clob_client_v2`` holds ONE module-level ``httpx.Client(http2=True)``
for the life of the process. When Polymarket's edge drops that connection,
the library turns the transport error into ``PolyApiException(status_code=
None, "Request exception!")``. Nothing retries a GET, and ``post`` retries
only when its caller asks (ours never did). The copy was lost and the
phone said "BUY not placed".

Here, a transport failure (no HTTP response at all) swaps in a fresh
client and sends the IDENTICAL request once more. For a GET that is plainly
safe. For an order POST it is safe because the body is the same signed
order: the exchange keys an order by its hash and tracks fills per hash, so
one signed order can never fill more than its size, however many times it
is posted. A reply with a status code (400, 404, 5xx) is the server
talking and is never retried here.

A leaf: imports only httpx, the library and the logger.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

import httpx

from src.logger import logger

_lock = threading.Lock()
TRANSPORT_MSG = "Request exception!"


def _is_transport_failure(exc: BaseException) -> bool:
    """The library's shape for "no HTTP response came back"."""
    return getattr(exc, "status_code", "x") is None and getattr(exc, "error_msg", None) == TRANSPORT_MSG


def fresh_client(helpers: Any, factory: Callable[[], Any] = lambda: httpx.Client(http2=True)) -> None:
    """Replace the library's shared client; close the dead one."""
    with _lock:
        old = getattr(helpers, "_http_client", None)
        helpers._http_client = factory()
    try:
        if old is not None:
            old.close()
    except Exception:  # noqa: BLE001  a dead connection may refuse to close cleanly
        pass


def install(helpers: Any = None, *, factory: Callable[[], Any] = lambda: httpx.Client(http2=True)) -> bool:
    """Wrap ``helpers.request`` once. ``get``/``post``/``delete`` look it up
    as a module global on every call, so the wrap covers them all. Returns
    True when this call installed it."""
    if helpers is None:
        from py_clob_client_v2.http_helpers import helpers  # noqa: PLW0621
    if getattr(helpers, "_pm_transport_retry", False):
        return False
    original = helpers.request

    def request(endpoint, method, headers=None, data=None, params=None):
        try:
            return original(endpoint, method, headers, data, params)
        except Exception as exc:  # noqa: BLE001
            if not _is_transport_failure(exc):
                raise
            path = str(endpoint).split("?")[0].split("//", 1)[-1].split("/", 1)[-1]
            logger.warn(f"[clob] connection dropped on {method} /{path}: fresh connection, sending the same request once more")
            fresh_client(helpers, factory)
            return original(endpoint, method, headers, data, params)

    helpers.request = request
    helpers._pm_transport_retry = True
    return True
