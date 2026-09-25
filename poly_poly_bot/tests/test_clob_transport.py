"""A dropped CLOB connection is replaced and the same request sent once
(2026-09-25: four live BUYs lost to "Request exception!")."""
from __future__ import annotations

import types

import httpx
import pytest
from py_clob_client_v2.exceptions import PolyApiException

from src.copy_trading import clob_transport


class _Client:
    def __init__(self, script):
        self.script, self.calls, self.closed = list(script), [], False

    def request(self, **kw):
        self.calls.append(kw)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def close(self):
        self.closed = True


def _resp(code, body='{"orderID": "0xabc"}'):
    return httpx.Response(code, text=body, request=httpx.Request("POST", "https://clob.polymarket.com/order"))


def _helpers(first_client):
    """A stand-in for the library module: the real request() body, run
    against whatever _http_client the module holds at call time."""
    from py_clob_client_v2.http_helpers import helpers as real
    mod = types.ModuleType("fake_helpers")
    mod._http_client = first_client
    mod.httpx = httpx
    mod.PolyApiException = PolyApiException
    mod.logger = real.logger
    mod._overload_headers = real._overload_headers
    orig = getattr(real, "_pm_original_request", real.request)    # the library's own, even once wrapped
    mod.request = types.FunctionType(orig.__code__, mod.__dict__, "request")
    return mod


def test_a_dropped_connection_is_replaced_and_the_identical_post_sent_once_more():
    dead = _Client([httpx.RemoteProtocolError("Server disconnected")])
    fresh = _Client([_resp(200)])
    h = _helpers(dead)
    assert clob_transport.install(h, factory=lambda: fresh) is True
    body = '{"order": {"salt": 1, "signature": "0xsig"}}'
    out = h.request("https://clob.polymarket.com/order", "POST", None, body)
    assert out == {"orderID": "0xabc"}
    assert dead.closed and h._http_client is fresh
    assert dead.calls[0]["content"] == fresh.calls[0]["content"] == body.encode(), "the same signed order, byte for byte"
    assert clob_transport.install(h, factory=lambda: fresh) is False, "wrapped once"


def test_a_server_answer_is_never_retried():
    c = _Client([_resp(400, '{"error": "not enough balance"}'), _resp(200)])
    h = _helpers(c)
    clob_transport.install(h, factory=lambda: pytest.fail("no fresh client for a 400"))
    with pytest.raises(PolyApiException) as e:
        h.request("https://clob.polymarket.com/order", "POST", None, "{}")
    assert e.value.status_code == 400 and len(c.calls) == 1


def test_a_second_drop_surfaces_as_before():
    h = _helpers(_Client([httpx.RemoteProtocolError("Server disconnected")]))
    clob_transport.install(h, factory=lambda: _Client([httpx.ReadError("again")]))
    with pytest.raises(PolyApiException) as e:
        h.request("https://clob.polymarket.com/book", "GET")
    assert e.value.status_code is None and e.value.error_msg == "Request exception!"


def test_the_real_library_is_wrapped_when_the_client_module_loads():
    from py_clob_client_v2.http_helpers import helpers
    import src.copy_trading.clob_client  # noqa: F401
    assert getattr(helpers, "_pm_transport_retry", False)
