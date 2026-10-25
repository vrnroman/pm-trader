"""Source families. Every HTTP family exposes the same three calls so the
poller is one loop over the roster:

    prepare(spec, state) -> (url, headers)        # conditional-GET headers from state
    handle(status, headers, body, spec, state, seen_ts) -> list[Item]   # pure; raises SourceError
    fetch(spec, state, client=None) -> list[Item]  # sync convenience: prepare + GET + handle

``state`` is a per-source dict the poller owns (ETag, Last-Modified, the
last cursor); the module may write to it. ``bluesky.stream`` is the one
websocket family and has its own shape.
"""

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
# The SEC rejects anonymous clients (403) and asks for a contact in the UA;
# the same string identifies us honestly to every other feed that logs it.
CONTACT_UA = "poly-news-bot vrnroman@gmail.com"
