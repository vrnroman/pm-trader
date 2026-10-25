"""Telegram channels through the real client API (MTProto, Telethon), as the
owner's own user account.

`telegram_web.py` scrapes t.me/s/<channel> every 30-60 s and only sees the
channels that left the web preview on. A logged-in user session instead
receives every channel post as a push update the moment it is sent, and
reads any channel the account can open. Nothing is sent from the account;
it reads and stays silent.

Config (env):
    TELEGRAM_API_ID        from https://my.telegram.org, "API development tools"
    TELEGRAM_API_HASH      same page
    TELEGRAM_USER_SESSION  a Telethon StringSession, minted once by
                           scripts/telegram_login.py on the owner's Mac; it
                           IS the login (as sensitive as the account password)
    NEWS_TGM_CHANNELS      optional comma list of extra channels (usernames,
                           @names or t.me links); the roster's "tg" channels
                           are always on the list

Items carry source ``tgm:<channel>`` so the roster, the brief and the lead
ledger tell the two Telegram paths apart; the dedup store keys on the same
``tgm:<channel>:<message id>`` so a post seen by both paths is still two
items (two sources, two clocks: that is the lag the thesis measures).
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from datetime import timezone

from src.logger import logger
from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, first_line, make_id

ENV_API_ID = "TELEGRAM_API_ID"
ENV_API_HASH = "TELEGRAM_API_HASH"
ENV_SESSION = "TELEGRAM_USER_SESSION"
ENV_CHANNELS = "NEWS_TGM_CHANNELS"

DEFAULT_DOMAINS = ("geo",)
MAX_BACKOFF_S = 60.0
BACKFILL_LIMIT = 20
# A link that stays up this long before dropping was a real session, not a
# server bouncing us: the next connect starts the backoff ladder over.
STABLE_LINK_S = 60.0
# Telethon counts the exact wait; one more second keeps us clear of its edge.
FLOOD_WAIT_MARGIN_S = 1.0

_TME = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?", re.I)
_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: str
    channels: tuple            # usernames as given (case kept for resolution)

    @property
    def ok(self) -> bool:
        return bool(self.api_id and self.api_hash and self.session)


def roster_channels(sources=None) -> list[str]:
    """The roster's Telegram channels (kind "tg"), in roster order."""
    from src.newsbot.sources import roster
    return [s.channel for s in (roster.V1 if sources is None else sources) if s.kind == "tg" and s.channel]


def roster_domains(sources=None) -> dict[str, tuple]:
    """lower-case channel -> domains, from the roster's "tg" entries."""
    from src.newsbot.sources import roster
    return {s.channel.lower(): tuple(s.domains) for s in (roster.V1 if sources is None else sources)
            if s.kind == "tg" and s.channel}


def normalize_channel(raw: str) -> str | None:
    """'@Visegrad_24', 'https://t.me/s/visegrad_24', 't.me/visegrad_24/1234'
    -> 'Visegrad_24' (case kept). Anything that is not a username (an
    invite link, a numeric id, an empty string) -> None."""
    s = (raw or "").strip()
    if not s:
        return None
    s = _TME.sub("", s)
    s = s.lstrip("@").split("/", 1)[0].split("?", 1)[0].strip()
    if s.startswith("+") or s.startswith("joinchat"):
        return None  # private invite links need a join; out of scope
    return s if _USERNAME.match(s) else None


def parse_channels(raw: str | None, defaults=()) -> list[str]:
    """Roster channels first, then the env extras, each once (case-insensitive)."""
    out: list[str] = []
    seen: set[str] = set()
    for cand in list(defaults) + re.split(r"[,\s]+", raw or ""):
        name = normalize_channel(cand)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def config_from_env(env=None, roster_sources=None) -> Config:
    env = os.environ if env is None else env
    raw_id = (env.get(ENV_API_ID) or "").strip()
    try:
        api_id = int(raw_id) if raw_id else 0
    except ValueError:
        api_id = 0
    return Config(
        api_id=api_id,
        api_hash=(env.get(ENV_API_HASH) or "").strip(),
        session=(env.get(ENV_SESSION) or "").strip(),
        channels=tuple(parse_channels(env.get(ENV_CHANNELS), roster_channels(roster_sources))),
    )


def enabled(env=None) -> bool:
    """All three credentials present (and the id numeric)."""
    return config_from_env(env).ok


# --------------------------------------------------------------------------
# Message -> Item
# --------------------------------------------------------------------------

def source_key(channel: str) -> str:
    return f"tgm:{channel.lower()}"


def post_url(channel: str, message_id) -> str:
    return f"https://t.me/{channel}/{message_id}"


def message_text(message) -> str:
    """The raw text, with the URLs that text-link entities hide behind
    words appended (the raw text already carries the visible ones)."""
    text = str(getattr(message, "message", None) or getattr(message, "text", None) or "").strip()
    for ent in getattr(message, "entities", None) or ():
        url = getattr(ent, "url", None)
        if isinstance(url, str) and url and url not in text:
            text = f"{text}\n{url}".strip()
    return text


def message_to_item(message, channel: str, seen_ts: float, domains: tuple = DEFAULT_DOMAINS) -> Item | None:
    """One Telethon Message -> Item, or None for a media-only post (nothing
    to judge) or a message without an id."""
    msg_id = getattr(message, "id", None)
    if msg_id is None:
        return None
    text = message_text(message)
    if not text:
        return None
    date = getattr(message, "date", None)
    published = None
    if date is not None:
        try:
            if getattr(date, "tzinfo", None) is None:
                date = date.replace(tzinfo=timezone.utc)
            published = float(date.timestamp())
        except (AttributeError, TypeError, ValueError, OverflowError):
            published = None
    if published is None:
        text = f"{NO_TIMESTAMP_FLAG} {text}"
        published = float(seen_ts)
    key = source_key(channel)
    return Item(
        id=make_id(key, str(msg_id)), source=key, domains=tuple(domains) or DEFAULT_DOMAINS,
        published_ts=published, seen_ts=float(seen_ts),
        title=first_line(text), text=text[:2000], url=post_url(channel, msg_id),
    )


async def fetch_recent(client, channel: str, limit: int = BACKFILL_LIMIT, *, domains: tuple = DEFAULT_DOMAINS,
                       seen_ts: float | None = None, entity=None) -> list[Item]:
    """The channel's last `limit` posts, oldest first, media-only skipped.
    One-off at connect so the first minutes are not empty; the caller dedups."""
    seen_ts = time.time() if seen_ts is None else seen_ts
    out: list[Item] = []
    async for msg in client.iter_messages(entity if entity is not None else channel, limit=limit):
        item = message_to_item(msg, channel, seen_ts, domains)
        if item is not None:
            out.append(item)
    out.reverse()
    return out


# --------------------------------------------------------------------------
# Telethon glue (every import of the library lives here so the tests, and a
# box without it, never touch it)
# --------------------------------------------------------------------------

def default_client_factory(cfg: Config):
    def factory():
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        # Telethon's own reconnect handles the short blips; the loop below
        # handles the long ones. Never save the session anywhere.
        return TelegramClient(StringSession(cfg.session), cfg.api_id, cfg.api_hash,
                              connection_retries=3, retry_delay=2, auto_reconnect=True)
    return factory


def _new_message_builder(chats):
    try:
        from telethon import events
    except ImportError:
        return None
    return events.NewMessage(chats=list(chats), incoming=None, outgoing=None)


def flood_wait_seconds(exc: BaseException) -> float | None:
    """Telethon's FloodWaitError (and its slow-mode cousins) carry `.seconds`;
    matched by shape so a fake in a test counts too."""
    secs = getattr(exc, "seconds", None)
    if isinstance(secs, (int, float)) and not isinstance(secs, bool) and "Flood" in type(exc).__name__:
        return float(secs)
    return None


def _peer_channel_id(event) -> int | None:
    """The bare channel id of an event, whichever way the client exposes it
    (peer_id.channel_id on the message, or the -100-prefixed chat_id)."""
    msg = getattr(event, "message", None)
    peer = getattr(msg, "peer_id", None)
    cid = getattr(peer, "channel_id", None)
    if cid is None:
        cid = getattr(event, "chat_id", None)
    if cid is None:
        return None
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    if cid < 0:
        s = str(-cid)
        cid = int(s[3:]) if s.startswith("100") and len(s) > 3 else -cid
    return cid


def _entity_id(entity) -> int | None:
    eid = getattr(entity, "id", None)
    try:
        return int(eid) if eid is not None else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# The stream
# --------------------------------------------------------------------------

async def stream(queue: asyncio.Queue, dedup, counters, *, stop: asyncio.Event, client_factory=None,
                 channels=None, domains_by_channel: dict[str, tuple] | None = None, env=None,
                 sleep=asyncio.sleep, clock=time.time, max_backoff_s: float = MAX_BACKOFF_S,
                 backfill_limit: int = BACKFILL_LIMIT) -> None:
    """Run until `stop` is set. Connect, resolve the channels, register one
    NewMessage handler for all of them, backfill the last `backfill_limit`
    posts per channel, then wait for the link to drop; reconnect with
    exponential backoff (1 s .. max_backoff_s). A FloodWaitError anywhere
    sleeps exactly what Telegram asked (plus a second) and does not grow
    the backoff."""
    cfg = config_from_env(env)
    if channels is None:
        channels = list(cfg.channels)
    channels = [c for c in (normalize_channel(c) for c in channels) if c]
    if domains_by_channel is None:
        domains_by_channel = roster_domains()
    domains_by_channel = {k.lower(): tuple(v) for k, v in domains_by_channel.items()}
    if client_factory is None:
        if not cfg.ok:
            logger.warn("[news-tgm] disabled: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_USER_SESSION not all set")
            return
        client_factory = default_client_factory(cfg)
    if not channels:
        logger.warn("[news-tgm] no channels to follow; not connecting")
        return

    def domains_for(channel: str) -> tuple:
        return domains_by_channel.get(channel.lower()) or DEFAULT_DOMAINS

    backoff = 1.0
    while not stop.is_set():
        client = client_factory()
        connected_at = None
        channel_by_id: dict[int, str] = {}
        got_message = False
        try:
            await client.connect()
            if hasattr(client, "is_user_authorized") and not await client.is_user_authorized():
                raise RuntimeError("session not authorized: mint a new TELEGRAM_USER_SESSION with scripts/telegram_login.py")
            connected_at = clock()
            entities = []
            for ch in channels:
                try:
                    ent = await client.get_entity(ch)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - UsernameNotOccupied, ChannelPrivate, FloodWait...
                    fw = flood_wait_seconds(e)
                    if fw is not None:
                        logger.warn(f"[news-tgm] flood wait {fw:.0f}s while resolving @{ch}")
                        await sleep(fw + FLOOD_WAIT_MARGIN_S)
                        try:
                            ent = await client.get_entity(ch)
                        except asyncio.CancelledError:
                            raise
                        except Exception as e2:  # noqa: BLE001
                            counters.error(source_key(ch), clock(), f"resolve: {e2}")
                            logger.warn(f"[news-tgm] channel @{ch} did not resolve err={type(e2).__name__}: {e2}")
                            continue
                    else:
                        counters.error(source_key(ch), clock(), f"resolve: {e}")
                        logger.warn(f"[news-tgm] channel @{ch} did not resolve err={type(e).__name__}: {e}")
                        continue
                eid = _entity_id(ent)
                if eid is None:
                    counters.error(source_key(ch), clock(), "resolve: entity without id")
                    continue
                channel_by_id[eid] = ch
                entities.append(ent)
            if not entities:
                raise RuntimeError("none of the channels resolved")

            async def on_new_message(event):
                nonlocal backoff, got_message
                ch = channel_by_id.get(_peer_channel_id(event) or -1)
                if ch is None:
                    return
                now = clock()
                item = message_to_item(getattr(event, "message", event), ch, now, domains_for(ch))
                if item is None:
                    return
                got_message = True
                backoff = 1.0
                if dedup is not None and not dedup.add(item.id):
                    return
                await queue.put(item)
                if counters is not None:
                    counters.ok(item.source, 1, now, item.published_ts)
                logger.info(f"[news-tgm] source={item.source} new=1 lag_s={now - item.published_ts:.1f} title={item.title[:80]!r}")

            client.add_event_handler(on_new_message, _new_message_builder(entities))
            logger.info(f"[news-tgm] connected channels={len(entities)}/{len(channels)}")

            # Backfill: the last few posts per channel so the first minutes are not empty.
            for ent in entities:
                ch = channel_by_id[_entity_id(ent)]
                try:
                    items = await fetch_recent(client, ch, backfill_limit, domains=domains_for(ch),
                                               seen_ts=clock(), entity=ent)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    fw = flood_wait_seconds(e)
                    if fw is not None:
                        logger.warn(f"[news-tgm] flood wait {fw:.0f}s during backfill of @{ch}; skipping its backfill")
                        await sleep(fw + FLOOD_WAIT_MARGIN_S)
                    else:
                        counters.error(source_key(ch), clock(), f"backfill: {e}")
                        logger.warn(f"[news-tgm] backfill failed @{ch} err={type(e).__name__}: {e}")
                    continue
                new = 0
                newest = None
                for item in items:
                    if dedup is not None and not dedup.add(item.id):
                        continue
                    await queue.put(item)
                    new += 1
                    newest = item.published_ts if newest is None else max(newest, item.published_ts)
                now = clock()
                counters.ok(source_key(ch), new, now, newest)
                logger.info(f"[news-tgm] backfill source={source_key(ch)} read={len(items)} new={new}")

            # Hold the link until it drops or we are told to stop.
            disconnected = asyncio.ensure_future(client.run_until_disconnected())
            stopper = asyncio.ensure_future(stop.wait())
            try:
                await asyncio.wait({disconnected, stopper}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for fut in (disconnected, stopper):
                    if not fut.done():
                        fut.cancel()
                # Surface the socket's own error (a drop) through the except below.
                if disconnected.done() and not disconnected.cancelled() and disconnected.exception() is not None:
                    raise disconnected.exception()
            if stop.is_set():
                break
            # run_until_disconnected returned: Telethon gave up reconnecting.
            raise ConnectionError("disconnected")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - every failure means "reconnect"
            fw = flood_wait_seconds(e)
            if fw is not None:
                logger.warn(f"[news-tgm] flood wait {fw:.0f}s; sleeping as asked")
                await sleep(fw + FLOOD_WAIT_MARGIN_S)
                continue
            if counters is not None:
                counters.error("tgm", clock(), str(e))
            if connected_at is not None and (got_message or clock() - connected_at >= STABLE_LINK_S):
                backoff = 1.0
            if stop.is_set():
                break
            logger.warn(f"[news-tgm] dropped err={type(e).__name__}: {e}; reconnecting in {backoff:.0f}s")
            await sleep(backoff)
            backoff = min(backoff * 2, max_backoff_s)
        finally:
            try:
                res = client.disconnect()
                if asyncio.iscoroutine(res) or isinstance(res, asyncio.Future):
                    await res
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - closing a dead socket
                pass
    logger.info("[news-tgm] stopped")
