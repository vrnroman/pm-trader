"""Credentials never reach a log file (2026-11-01, s-wj4gnb: aiosqlite's DEBUG
query log wrote the owner's X session cookies into bot-*.log)."""

import logging

from src.logger import SecretScrubFilter, scrub_secrets

AUTH = "863c" + "0" * 36
CT0 = "e3ca" + "f" * 156


def test_cookie_json_and_header_shapes_are_redacted():
    js = '{"username": "cookie-session", "cookies": \'{"auth_token": "%s", "ct0": "%s"}\'}' % (AUTH, CT0)
    out = scrub_secrets(js)
    assert AUTH not in out and CT0 not in out and out.count("***REDACTED") == 2
    hdr = f"Cookie: auth_token={AUTH}; ct0={CT0}"
    out = scrub_secrets(hdr)
    assert AUTH not in out and CT0 not in out


def test_ordinary_text_is_untouched():
    for t in ("ct0 rotation planned", "auth_token: missing", "ok"):
        assert scrub_secrets(t) == t


def test_the_root_file_handler_drops_third_party_debug_and_scrubs_info(tmp_path, monkeypatch):
    """Drive main._setup_logging: an aiosqlite DEBUG record carrying the
    cookies must not be written; an INFO one with them is written scrubbed."""
    import dataclasses

    import main
    monkeypatch.setattr(main, "CONFIG", dataclasses.replace(main.CONFIG, logs_dir=str(tmp_path)))
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        main._setup_logging()
        lg = logging.getLogger("aiosqlite.probe")
        lg.setLevel(logging.DEBUG)
        lg.debug('INSERT cookies {"auth_token": "%s"}', AUTH)
        lg.info('upsert {"ct0": "%s"}', CT0)
        for h in root.handlers:
            h.flush()
        text = "".join(p.read_text() for p in tmp_path.glob("bot-*.log"))
        assert AUTH not in text and CT0 not in text
        assert "upsert" in text and "***REDACTED" in text
        assert "INSERT cookies" not in text, "third-party DEBUG never reaches the file"
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
    assert isinstance(SecretScrubFilter(), logging.Filter)
