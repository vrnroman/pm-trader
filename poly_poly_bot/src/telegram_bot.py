"""Telegram bot for the copy-trading strategy (Strategy #1).

Commands:
  /status            — Show bot status (balance, positions, daily limits)
  /pnl               — Show P&L: realized + unrealized
  /history           — Show last 10 copy trades
  /check             — Verify trading setup (read-only, no orders)
  /setkey            — Rotate/clear the in-memory private key
  /shutdown          — Graceful shutdown (Docker restarts the container)
  /help              — Show available commands

The Weather (#2) and Tennis Arb (#3) strategies were decommissioned on
2026-06-17; see DECOMMISSIONED.md to restore them from git history.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests

from src.config import CONFIG

logger = logging.getLogger("telegram")

SGT = timezone(timedelta(hours=8))


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Commands registered in the Telegram popup menu (setMyCommands).
# Names must match ^[a-z0-9_]{1,32}$ — Telegram rejects the entire batch
# otherwise. Every name listed here MUST also be dispatched in
# ``_handle_command``; the parity is enforced by
# ``tests/test_telegram_handlers.py::test_bot_menu_matches_dispatcher``.
BOT_MENU_COMMANDS: list[dict] = [
    {"command": "start", "description": "Show all commands"},
    {"command": "help", "description": "Show all commands"},
    {"command": "status", "description": "Balance, positions, daily limits"},
    {"command": "pnl", "description": "P&L by strategy: realized + unrealized + total"},
    {"command": "wallets", "description": "3 best & worst wallets per strategy (by PnL & ROI)"},
    {"command": "history", "description": "Last 10 copy trades"},
    {"command": "check", "description": "Verify trading setup (read-only, no orders)"},
    {"command": "setkey", "description": "Rotate/clear in-memory private key (e.g. /setkey clear CONFIRM)"},
    {"command": "reset", "description": "Zero all P&L + risk/spend state (archives first; needs CONFIRM)"},
    {"command": "shutdown", "description": "Graceful shutdown (Docker restarts container)"},
]

_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()

# Callbacks set by main.py
on_refresh_clob_client = None  # Callable[[], None] — rebuild CLOB client after /setkey


def is_configured() -> bool:
    """Check if Telegram bot is configured."""
    return bool(CONFIG.telegram_bot_token) and bool(CONFIG.telegram_chat_id)


def send_message(text: str, parse_mode: str = "HTML"):
    """Send a message to the configured Telegram chat."""
    if not is_configured():
        return
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": CONFIG.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }, timeout=10)
        if not resp.ok:
            logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")


def _send_chunked(text: str, parse_mode: str = "HTML", chunk_size: int = 3800):
    """Send a potentially long message as multiple Telegram messages.

    Splits on newline boundaries. We rely on the convention that HTML tags
    used here (<b>, <code>, <i>) open and close on the same line, so a split
    between lines won't tear a tag.
    """
    if len(text) <= chunk_size:
        send_message(text, parse_mode=parse_mode)
        return

    buf: list[str] = []
    cur = 0
    for line in text.split("\n"):
        ln = len(line) + 1  # +1 for the newline we re-insert
        if buf and cur + ln > chunk_size:
            send_message("\n".join(buf), parse_mode=parse_mode)
            buf = []
            cur = 0
        buf.append(line)
        cur += ln
    if buf:
        send_message("\n".join(buf), parse_mode=parse_mode)


# --- Live price fetching ---

def _fetch_midpoint(token_id: str) -> float | None:
    """Fetch current midpoint price for a YES token from CLOB API."""
    try:
        resp = requests.get(
            f"{CONFIG.clob_api_url}/midpoint",
            params={"token_id": token_id},
            timeout=5,
        )
        if resp.ok:
            data = resp.json()
            mid = data.get("mid")
            if mid is not None:
                return float(mid)
    except Exception as e:
        logger.debug(f"Midpoint fetch failed for {token_id[:20]}...: {e}")
    return None


def _load_s1_trades() -> list[dict]:
    """Load Strategy #1 copy trading trade history."""
    history_path = os.path.join(CONFIG.data_dir, "trade-history.jsonl")
    if not os.path.exists(history_path):
        return []
    trades = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return trades


# --- Command handlers ---

def _handle_command(text: str):
    """Process a telegram command."""
    text = text.strip()

    if text.startswith("/history"):
        _handle_history()
    elif text.startswith("/status"):
        _handle_status()
    elif text.startswith("/pnl"):
        _handle_pnl()
    elif text.startswith("/wallets"):
        _handle_wallets()
    elif text.startswith("/check"):
        _handle_check()
    elif text.startswith("/setkey"):
        _handle_setkey(text)
    elif text.startswith("/reset"):
        _handle_reset(text)
    elif text.startswith("/shutdown"):
        _handle_shutdown(text)
    elif text.startswith("/help") or text.startswith("/start"):
        _handle_help()
    else:
        return


def _handle_status():
    """Handle /status command — show Strategy #1 status."""
    now = datetime.now(SGT)

    lines = [
        f"<b>Bot Status</b>",
        f"Time: {now.strftime('%Y-%m-%d %H:%M SGT')}",
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}",
        "",
    ]

    # Strategy #1 — Copy Trading
    lines.append(f"<b>Strategy #1 — Copy Traders</b>")
    if CONFIG.strategy1_enabled:
        lines.append("Status: \U0001f7e2 ENABLED")
        lines.append(f"Wallets tracked: {len(CONFIG.user_addresses)}")
        lines.append(f"Copy strategy: {CONFIG.copy_strategy}")
        lines.append(f"Copy size: ${CONFIG.copy_size:.0f}")
        s1_trades = _load_s1_trades()
        if s1_trades:
            total_cost = sum((t.get("cost") or 0) for t in s1_trades)
            lines.append(f"Total deployed: ${total_cost:.2f}")
            lines.append(f"Total trades: {len(s1_trades)}")
    else:
        lines.append("Status: ⚪ DISABLED")

    send_message("\n".join(lines))


def _short_wallet(w: str) -> str:
    """0x1234…cdef — compact wallet address for leaderboard lines."""
    w = w or ""
    return f"{w[:6]}…{w[-4:]}" if len(w) > 12 else (w or "—")


def _compute_unified():
    """Build the unified per-strategy / per-wallet P&L across both copy systems.

    System A = tiered executor (``realized-pnl.jsonl`` + open inventory marked to
    midpoint, attributed by tier/trader). System B = the paper-copy harness
    ledger (attributed by ``target`` wallet + discovery theories). Returns
    ``(unified, a_wallets, b_wallets, n_unpriced)`` so /pnl and /wallets share
    one computation.
    """
    from src.copy_trading import inventory
    from src.copy_trading import pnl as s1pnl
    from src.copy_trading import pnl_unified as u
    from src.copy_trading.copy_paper import PaperCopyLedger
    from src.copy_trading.copy_paper_live import load_watchlist_flagged_by
    from src.copy_trading.strategy_config import get_wallet_tier

    # System A — tiered executor
    realized_rows = s1pnl.load_realized()
    positions = inventory.get_positions()
    open_pos = s1pnl.value_open_positions(positions, _fetch_midpoint, fee=0.0)
    n_unpriced = sum(1 for p in open_pos if p.unrealized_pnl is None)
    a_wallets = u.aggregate_system_a(realized_rows, open_pos, tier_of=get_wallet_tier)

    # System B — paper-copy harness
    try:
        ledger = PaperCopyLedger(CONFIG.copy_paper_ledger)
        paper_positions = list(ledger.positions.values())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"copy-paper ledger load failed: {e}")
        paper_positions = []
    flagged_now = load_watchlist_flagged_by(CONFIG.copy_paper_watchlist)
    b_wallets = u.aggregate_system_b(paper_positions, flagged_now)

    unified = u.build_unified(a_wallets, b_wallets)
    return unified, a_wallets, b_wallets, n_unpriced


def _handle_pnl():
    """Handle /pnl — unified P&L: overall total + per-strategy breakdown.

    Strategy labels are ``A:1a``/``A:1b``/``A:1c`` (executor tiers) and
    ``B:1a``..``B:1j`` (discovery theories the paper-copied wallet was flagged
    by), plus ``untagged-*`` for un-attributed positions."""
    unified, a_wallets, b_wallets, n_unpriced = _compute_unified()

    all_w = a_wallets + b_wallets
    total_open = sum(w.n_open for w in all_w)
    total_closed = sum(w.n_closed for w in all_w)
    wins = sum(w.wins for w in all_w)
    losses = sum(w.losses for w in all_w)

    lines = ["\U0001f4ca <b>P&amp;L Report</b>", ""]
    lines.append("<b>TOTAL</b>")
    lines.append(f"  Realized:    ${unified.total_realized:+.2f}")
    lines.append(f"  Unrealized:  ${unified.total_unrealized:+.2f}")
    lines.append(f"  Net:         ${unified.total_net:+.2f}")
    lines.append(f"  Open bets:   {total_open}")
    if total_closed:
        hit = wins / total_closed if total_closed else 0.0
        lines.append(f"  Record:      {wins}W/{losses}L ({hit:.0%} hit)")
    if n_unpriced:
        lines.append(f"  ⚠ {n_unpriced} position(s) unpriced (no live quote)")

    lines.append("")
    lines.append("<b>By strategy</b>  <i>(net | realized/unrealized | ROI | wallets | closed/open)</i>")
    if not unified.strategies:
        lines.append("  (no positions yet)")
    for sp in unified.strategies:
        roi = sp.roi
        roi_str = f"ROI {roi:+.0%}" if roi is not None else "ROI n/a"
        if sp.system == "A":
            pnl_str = f"r ${sp.realized_pnl:+.0f}/u ${sp.unrealized_pnl:+.0f}"
        else:
            pnl_str = f"r ${sp.realized_pnl:+.0f}"
        lines.append(
            f"<code>{_esc(sp.label)}</code>  ${sp.net_pnl:+.2f}  ({pnl_str}, {roi_str})  "
            f"— {sp.n_wallets}w {sp.n_closed}c/{sp.n_open}o"
        )

    lines.append("")
    lines.append("<i>/wallets — 3 best &amp; worst wallets per strategy</i>")
    if CONFIG.preview_mode:
        lines.append("<i>PREVIEW MODE — positions are simulated</i>")

    _send_chunked("\n".join(lines))


def _wallet_line(w) -> str:
    """One leaderboard row: addr, net P&L, ROI, win/loss record."""
    roi = w.roi
    roi_str = f"ROI {roi:+.0%}" if roi is not None else "ROI n/a"
    rec = f", {w.wins}W/{w.losses}L" if (w.wins + w.losses) else ""
    return f"<code>{_short_wallet(w.wallet)}</code> ${w.net_pnl:+.2f} ({roi_str}{rec})"


def _handle_wallets():
    """Handle /wallets — per strategy, the 3 best & 3 worst wallets by P&L and
    by ROI. These are the promote-to-real-money / drop candidates."""
    from src.copy_trading import pnl_unified as u

    unified, _a, _b, _n = _compute_unified()
    if not unified.strategies:
        send_message("\U0001f3c5 <b>Wallet leaderboard</b>\nNo positions yet.")
        return

    lines = [
        "\U0001f3c5 <b>Wallet leaderboard</b> <i>(promotion / removal candidates)</i>",
        "",
    ]
    for sp in unified.strategies:
        bw = u.best_worst(sp.wallets, k=3)
        lines.append(f"<b>{_esc(sp.label)}</b>  ({sp.n_wallets}w)")
        lines.append("  ▲ best PnL:")
        for w in bw.by_pnl_best:
            lines.append("     " + _wallet_line(w))
        lines.append("  ▼ worst PnL:")
        for w in bw.by_pnl_worst:
            lines.append("     " + _wallet_line(w))
        if bw.by_roi_best:
            lines.append("  ▲ best ROI:")
            for w in bw.by_roi_best:
                lines.append("     " + _wallet_line(w))
            lines.append("  ▼ worst ROI:")
            for w in bw.by_roi_worst:
                lines.append("     " + _wallet_line(w))
        lines.append("")

    _send_chunked("\n".join(lines))


def _handle_history():
    """Handle /history command — show last 10 copy trades (Strategy #1)."""
    if not CONFIG.strategy1_enabled:
        send_message("Strategy #1 (Copy Trading) is disabled.")
        return

    trades = _load_s1_trades()
    if not trades:
        send_message("<b>Strategy #1 — Copy Trading History</b>\nNo trades yet.")
        return

    recent = trades[-10:]
    lines = [
        f"<b>Strategy #1 — Last {len(recent)} Copy Trades</b>",
        "",
    ]

    for t in reversed(recent):
        ts = t.get("timestamp", "?")
        if isinstance(ts, str) and len(ts) > 16:
            ts = ts[:16]
        market = _esc(t.get("market_question", t.get("market", "?"))[:40])
        side = t.get("side", "?")
        size = t.get("size_usd", t.get("cost", 0))
        price = t.get("price", 0)
        status = t.get("status", "?")
        pnl = t.get("pnl")

        pnl_str = f" | PnL: ${pnl:+.2f}" if pnl is not None else ""
        lines.append(
            f"<code>{ts}</code> {side} ${size:.1f} @ {price:.1%}\n"
            f"  {market}\n"
            f"  Status: {status}{pnl_str}"
        )

    send_message("\n".join(lines))


def _handle_setkey(text: str):
    """Handle /setkey <hex|clear> CONFIRM — rotate or wipe the in-memory key.

    Safety lever to immediately invalidate signed orders. Change is in-memory
    only; on container restart the .env value reloads. Strategy #1's running
    loops hold the CLOB client obtained at startup, so a rotated key fully
    takes effect on the next restart.
    """
    from src.config import set_private_key

    parts = text.split()
    # /setkey <hex|clear> CONFIRM  (3 tokens)
    if len(parts) != 3 or parts[2] != "CONFIRM":
        send_message(
            "Usage:\n"
            "<code>/setkey clear CONFIRM</code> — wipe in-memory key (no orders signable)\n"
            "<code>/setkey 0xABCD... CONFIRM</code> — replace key in memory\n"
            "Change is in-memory only; container restart reloads .env."
        )
        return

    arg = parts[1]
    if arg.lower() == "clear":
        set_private_key("")
        if on_refresh_clob_client:
            try:
                on_refresh_clob_client()
            except Exception as e:
                logger.exception("Refresh CLOB client failed")
                send_message(f"Key cleared but refresh failed: <code>{_esc(str(e))}</code>")
                return
        send_message(
            "🛑 Private key <b>cleared</b> in memory. "
            "CLOB client invalidated; live trading cannot sign new orders. "
            "Restart will reload the .env key."
        )
        logger.warning("PRIVATE_KEY cleared in memory via /setkey")
        return

    try:
        new_key = set_private_key(arg)
    except ValueError as e:
        send_message(f"Invalid key: <code>{_esc(str(e))}</code>")
        return

    if on_refresh_clob_client:
        try:
            on_refresh_clob_client()
        except Exception as e:
            logger.exception("Refresh CLOB client failed")
            send_message(f"Key updated but CLOB rebuild failed: <code>{_esc(str(e))}</code>")
            return

    # Derive EOA so user can sanity-check that the new key matches what
    # they intended. We do NOT echo the key itself.
    try:
        from web3 import Web3
        eoa = Web3().eth.account.from_key(f"0x{new_key}").address
    except Exception:
        eoa = "<unknown>"
    send_message(
        f"🔑 Private key <b>updated</b> in memory. New EOA: <code>{eoa}</code>. "
        "Restart will reload the .env key."
    )
    logger.warning(f"PRIVATE_KEY rotated in memory via /setkey (EOA={eoa})")


def _handle_reset(text: str):
    """Handle /reset CONFIRM — zero all P&L + risk/spend state (archives first).

    Clears both copy systems' ledgers/state and the executor's in-memory
    counters. The paper-copy harness holds its ledger in memory in a daemon
    thread, so to fully clear System B you must restart: this prompts a
    /shutdown so the container comes back up on the empty ledger. For a
    guaranteed-clean reset, run ``python -m scripts.reset_pnl --confirm`` on the
    VM with the bot stopped.
    """
    parts = text.split()
    if len(parts) != 2 or parts[1] != "CONFIRM":
        send_message(
            "Usage: <code>/reset CONFIRM</code>\n"
            "Zeroes <b>all</b> P&amp;L + risk/spend state for both copy systems "
            "(archives a timestamped backup first). Open/unredeemed bets are dropped.\n"
            "After it runs, send <code>/shutdown CONFIRM</code> so the paper "
            "harness restarts on the empty ledger."
        )
        return

    from src.copy_trading.reset_pnl import reset_pnl

    res = reset_pnl(CONFIG.data_dir, confirm=True, copy_paper_ledger=CONFIG.copy_paper_ledger)
    logger.warning("P&L reset via /reset CONFIRM")
    send_message(
        "🧹 <b>P&amp;L reset</b> — " + _esc(res.summary()) + ".\n"
        "Executor + risk/spend state zeroed and backed up to <code>data/archive/</code>.\n"
        "The paper-copy harness keeps its ledger in memory — send "
        "<code>/shutdown CONFIRM</code> now to restart it on the empty ledger "
        "(Docker brings the container back automatically)."
    )


def _handle_shutdown(text: str):
    """Handle /shutdown CONFIRM — graceful process exit.

    Docker is configured with --restart unless-stopped, so the container
    will come back up automatically — but on restart it reloads from .env
    where PREVIEW_MODE=true is the default. To physically stop the
    container, SSH the VM and ``docker stop poly-poly-bot``.
    """
    parts = text.split()
    if len(parts) != 2 or parts[1] != "CONFIRM":
        send_message(
            "Usage: <code>/shutdown CONFIRM</code>\n"
            "Exits the bot process. Docker will restart it within seconds; "
            "the restart will read PREVIEW_MODE from .env (currently true). "
            "For permanent stop, SSH the VM and run "
            "<code>docker stop poly-poly-bot</code>."
        )
        return

    send_message("👋 Shutting down. Container will restart per Docker policy.")
    logger.warning("Bot shutdown requested via /shutdown")
    # Kick off a delayed hard exit so the Telegram send_message above flushes.
    def _delayed_exit():
        import time
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()


def _handle_check():
    """Handle /check — read-only verification of trading setup.

    Runs through PRIVATE_KEY, PROXY_WALLET, CLOB auth, USDC balance, and
    on-chain approvals on both Polymarket exchanges. Posts nothing on chain
    and submits no orders.
    """
    from src.config import CONFIG, get_private_key

    lines: list[str] = ["🔧 <b>Setup Check</b>", ""]
    ok_all = True

    # 1. Private key + derived EOA
    pk = get_private_key()
    eoa = ""
    if not pk:
        lines.append("❌ <b>PRIVATE_KEY</b>: not configured")
        send_message("\n".join(lines))
        return
    try:
        from web3 import Web3
        eoa = Web3().eth.account.from_key(f"0x{pk}").address
        lines.append(f"✅ PRIVATE_KEY → EOA <code>{eoa}</code>")
    except Exception as e:
        lines.append(f"❌ PRIVATE_KEY invalid: <code>{_esc(str(e))}</code>")
        send_message("\n".join(lines))
        return

    # 2. PROXY_WALLET
    proxy = CONFIG.proxy_wallet
    if not proxy:
        lines.append("❌ <b>PROXY_WALLET</b>: not set in .env")
        ok_all = False
    else:
        lines.append(f"✅ PROXY_WALLET <code>{proxy}</code>")

    # 3. SIGNATURE_TYPE
    sig_type = CONFIG.signature_type
    sig_label = {0: "EOA (no proxy)", 1: "POLY_PROXY (email login)", 2: "POLY_GNOSIS_SAFE (browser wallet)"}.get(sig_type, f"unknown({sig_type})")
    lines.append(f"   SIGNATURE_TYPE: {sig_type} — {sig_label}")

    # 4. USDC balance on proxy
    if proxy:
        try:
            from src.constants import ERC20_BALANCE_ABI, USDC_ADDRESS
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
            usdc = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_BALANCE_ABI,
            )
            raw = usdc.functions.balanceOf(Web3.to_checksum_address(proxy)).call()
            usdc_bal = raw / 1_000_000
            mark = "✅" if usdc_bal > 0 else "⚠️"
            lines.append(f"{mark} USDC balance: <b>${usdc_bal:.2f}</b>")
            if usdc_bal == 0:
                lines.append("   <i>Proxy is empty — fund it before going live.</i>")
                ok_all = False
        except Exception as e:
            lines.append(f"❌ USDC balance lookup failed: <code>{_esc(str(e))}</code>")
            ok_all = False

    # 5. CLOB authentication (read-only — derives API creds from L1 sig)
    clob_client = None
    try:
        from src.copy_trading.clob_client import create_clob_client
        clob_client = create_clob_client()
        if clob_client is None:
            lines.append("❌ CLOB client: not created (private key issue?)")
            ok_all = False
        else:
            lines.append("✅ CLOB client authenticated")
    except Exception as e:
        lines.append(f"❌ CLOB auth failed: <code>{_esc(str(e))}</code>")
        ok_all = False

    # 6. On-chain approvals (read-only)
    if proxy:
        try:
            from src.constants import (
                CTF_CONTRACT,
                CTF_EXCHANGE,
                ERC1155_APPROVAL_ABI,
                ERC20_APPROVE_ABI,
                NEG_RISK_CTF_EXCHANGE,
                USDC_ADDRESS,
            )
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
            usdc = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_APPROVE_ABI,
            )
            ctf = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_CONTRACT),
                abi=ERC1155_APPROVAL_ABI,
            )
            threshold = 10**6 * 10**6  # 1M USDC
            owner = Web3.to_checksum_address(proxy)
            for name, exchange in [("CTF", CTF_EXCHANGE), ("NegRisk", NEG_RISK_CTF_EXCHANGE)]:
                addr = Web3.to_checksum_address(exchange)
                allowance = usdc.functions.allowance(owner, addr).call()
                approved = ctf.functions.isApprovedForAll(owner, addr).call()
                u_ok = "✅" if allowance >= threshold else "❌"
                c_ok = "✅" if approved else "❌"
                lines.append(f"   {name}: USDC {u_ok}  CTF {c_ok}")
                if allowance < threshold or not approved:
                    ok_all = False
        except Exception as e:
            lines.append(f"❌ Approval check failed: <code>{_esc(str(e))}</code>")
            ok_all = False

    # 7. Authenticated CLOB read — confirms creds work end-to-end
    if clob_client is not None and proxy:
        try:
            from py_clob_client_v2 import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            ba = clob_client.get_balance_allowance(params)
            lines.append(f"✅ CLOB /balance-allowance OK: {ba}")
        except Exception as e:
            lines.append(f"⚠️ CLOB authed read failed: <code>{_esc(str(e))}</code>")

    lines.append("")
    lines.append("<b>READY</b> ✅" if ok_all else "<b>NOT READY</b> ❌ — fix items above before going live (PREVIEW_MODE=false)")
    _send_chunked("\n".join(lines))


def _handle_help():
    """Handle /help command."""
    send_message(
        "<b>Polymarket Copy-Trading Bot — Commands</b>\n\n"
        "<b>Strategy #1 — Copy Trading</b>\n"
        "<code>/status</code> — Bot status, balance, positions\n"
        "<code>/pnl</code> — P&amp;L by strategy: realized + unrealized + total\n"
        "<code>/wallets</code> — 3 best &amp; worst wallets per strategy (PnL &amp; ROI)\n"
        "<code>/history</code> — Last 10 copy trades\n"
        "<code>/check</code> — Verify trading setup (read-only)\n\n"
        "<b>Safety levers</b>\n"
        "<code>/setkey clear CONFIRM</code> — Wipe in-memory private key\n"
        "<code>/setkey 0xHEX CONFIRM</code> — Replace key in memory\n"
        "<code>/reset CONFIRM</code> — Zero all P&amp;L + risk/spend state (archives first)\n"
        "<code>/shutdown CONFIRM</code> — Graceful exit (container will restart)\n\n"
        "<code>/help</code> — Show this message\n\n"
        f"Strategy #1: {'ON' if CONFIG.strategy1_enabled else 'OFF'}\n"
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}"
    )


# --- Polling ---

def _process_update(update: dict) -> None:
    """Filter, parse, and dispatch a single Telegram getUpdates entry.

    Extracted from ``_poll_loop`` so the chat-id filter, command-prefix
    filter, and exception wrapper are unit-testable without standing up
    a polling thread. The wrapper is the kill-switch's safety net: if a
    handler raises, we log it and surface the error to the user instead
    of letting the exception kill the polling thread (and with it, all
    future Telegram control of the bot).
    """
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")

    if chat_id != CONFIG.telegram_chat_id:
        return

    if not text:
        return

    if text.startswith("/"):
        logger.info(f"Telegram command: {text}")
        try:
            _handle_command(text)
        except Exception as e:
            logger.exception(f"Command handler error: {e}")
            send_message(f"Error: <code>{_esc(str(e))}</code>")
        return


def _poll_loop():
    """Poll Telegram for new messages."""
    last_update_id = 0

    # Flush stale updates
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/getUpdates"
        resp = requests.get(url, params={"offset": -1, "timeout": 0}, timeout=10)
        if resp.ok:
            data = resp.json()
            results = data.get("result", [])
            if results:
                last_update_id = results[-1]["update_id"] + 1
    except Exception:
        pass

    logger.info("Telegram polling started")

    while not _stop_event.is_set():
        try:
            url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/getUpdates"
            resp = requests.get(url, params={
                "offset": last_update_id,
                "timeout": 10,
                "allowed_updates": '["message"]',
            }, timeout=15)

            if not resp.ok:
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                last_update_id = update["update_id"] + 1
                _process_update(update)

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")
            time.sleep(5)


def _register_bot_menu():
    """Register all bot commands in the Telegram UI menu.

    Telegram rejects the entire batch (HTTP 200 with ok=false) if any single
    command name violates ^[a-z0-9_]{1,32}$. We surface that rejection in
    logs and on Telegram so a typo doesn't silently wipe the popup menu.

    Telegram resolves the popup menu per chat by picking the most-specific
    scope that has commands set: chat_member > chat_administrators > chat >
    all_chat_administrators > all_private_chats / all_group_chats > default.
    A stale list on any narrower scope hides our default-scope list — so
    before we register the default, we clear every broader-than-default
    scope we ever might have set. (Per-chat scopes can only be set by
    explicit chat_id and aren't touched here.)
    """
    base = TELEGRAM_API.format(token=CONFIG.telegram_bot_token)

    # Wipe scoped command lists that would shadow the default scope.
    for scope in (
        {"type": "all_private_chats"},
        {"type": "all_group_chats"},
        {"type": "all_chat_administrators"},
    ):
        try:
            r = requests.post(f"{base}/deleteMyCommands", json={"scope": scope}, timeout=10)
            if not (r.ok and r.json().get("ok")):
                logger.warning(f"deleteMyCommands {scope['type']} failed: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"deleteMyCommands {scope['type']} error: {e}")

    try:
        resp = requests.post(f"{base}/setMyCommands", json={"commands": BOT_MENU_COMMANDS}, timeout=10)
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        if resp.ok and body.get("ok"):
            logger.info("Telegram menu: registered %d commands", len(BOT_MENU_COMMANDS))
        else:
            err = body.get("description") or f"HTTP {resp.status_code}"
            logger.error(f"Telegram setMyCommands rejected: {err}")
            try:
                send_message(f"⚠️ Telegram menu update failed: <code>{_esc(err)}</code>")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Telegram setMyCommands error: {e}")


def start_polling():
    """Start telegram polling in a background thread."""
    global _poll_thread
    if not is_configured():
        logger.info("Telegram not configured, skipping poll")
        return
    _register_bot_menu()
    _stop_event.clear()
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-poll")
    _poll_thread.start()
    logger.info("Telegram polling thread started")


def stop_polling():
    """Stop telegram polling."""
    _stop_event.set()
    if _poll_thread:
        _poll_thread.join(timeout=15)
    logger.info("Telegram polling stopped")
