"""Unified configuration for the copy-trading bot (Strategy #1).

The Weather (#2) and Tennis Arb (#3) strategies were decommissioned on
2026-06-17; see DECOMMISSIONED.md to restore them from git history.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from src.config_validators import parse_addresses, validate_private_key, validate_address

# Load .env from project root (poly_poly_bot/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ValueError(f"Missing required env var: {name}")
    return val


def _optional(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


def _opt_float(name: str, fallback: float) -> float:
    v = os.environ.get(name, "").strip()
    return float(v) if v else fallback


def _opt_int(name: str, fallback: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else fallback


def _opt_bool(name: str, fallback: bool) -> bool:
    v = os.environ.get(name, "").strip()
    if not v:
        return fallback
    return v.lower() == "true"


# --- Strategy 1 (Copy Trading) wallet loading ---

def _load_user_addresses() -> list[str]:
    """Load tracked wallets from USER_ADDRESSES or tiered strategy wallets."""
    raw = os.environ.get("USER_ADDRESSES", "").strip()
    if raw:
        addrs = parse_addresses(raw)
        for addr in addrs:
            validate_address(addr, "USER_ADDRESSES entry")
        return addrs
    tier1a = os.environ.get("STRATEGY_1A_WALLETS", "").strip()
    tier1b = os.environ.get("STRATEGY_1B_WALLETS", "").strip()
    if tier1a or tier1b:
        all_addrs: set[str] = set()
        if tier1a:
            for a in parse_addresses(tier1a):
                validate_address(a, "STRATEGY_1A_WALLETS")
                all_addrs.add(a)
        if tier1b:
            for a in parse_addresses(tier1b):
                validate_address(a, "STRATEGY_1B_WALLETS")
                all_addrs.add(a)
        return list(all_addrs)
    return []


def _load_private_key() -> str:
    """Load and validate private key, then remove from env."""
    raw = os.environ.get("PRIVATE_KEY", "").strip()
    if not raw:
        return ""
    validated = validate_private_key(raw)
    # Remove from env immediately — module const is the single source
    if "PRIVATE_KEY" in os.environ:
        del os.environ["PRIVATE_KEY"]
    return validated


_private_key = _load_private_key()


def get_private_key() -> str:
    """Access validated private key."""
    return _private_key


def set_private_key(raw: str) -> str:
    """Replace the in-memory private key at runtime.

    Used by the Telegram /setkey command as a safety lever: rotating to a
    different key (or clearing it with the empty string) immediately
    prevents the bot from signing further orders without redeploying.

    Returns the validated 64-hex key (or empty string when cleared).
    Raises ``ValueError`` on a bad hex.
    """
    global _private_key
    raw = (raw or "").strip()
    if not raw:
        _private_key = ""
        return ""
    _private_key = validate_private_key(raw)
    return _private_key


# Determine which strategies are enabled
_s1a_enabled = _opt_bool("STRATEGY_1A_ENABLED", bool(os.environ.get("STRATEGY_1A_WALLETS", "").strip()))
_s1b_enabled = _opt_bool("STRATEGY_1B_ENABLED", bool(os.environ.get("STRATEGY_1B_WALLETS", "").strip()))
_s1c_enabled = _opt_bool("STRATEGY_1C_ENABLED", False)
_strategy1_enabled = _s1a_enabled or _s1b_enabled or _s1c_enabled

_user_addresses = _load_user_addresses()

# Validate proxy wallet only when Strategy 1 is enabled
_proxy_wallet = ""
if _strategy1_enabled and os.environ.get("PROXY_WALLET", "").strip():
    _proxy_wallet = validate_address(_required("PROXY_WALLET"), "PROXY_WALLET")


class Config:
    """Unified configuration for all strategies."""

    # --- Strategy toggles ---
    strategy1_enabled: bool = _strategy1_enabled

    # --- Global ---
    preview_mode: bool = _opt_bool("PREVIEW_MODE", True)
    telegram_bot_token: str = _optional("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = _optional("TELEGRAM_CHAT_ID", "")

    # --- Strategy 1: Copy Trading ---
    user_addresses: list[str] = _user_addresses
    proxy_wallet: str = _proxy_wallet
    signature_type: int = _opt_int("SIGNATURE_TYPE", 0)

    copy_strategy: str = _optional("COPY_STRATEGY", "PERCENTAGE")
    copy_size: float = _opt_float("COPY_SIZE", 10.0)
    max_order_size_usd: float = _opt_float("MAX_ORDER_SIZE_USD", 100.0)
    min_order_size_usd: float = _opt_float("MIN_ORDER_SIZE_USD", 1.0)
    # Maximum slippage we accept on a live limit order, in basis points.
    # The order is posted at best_ask × (1 + slippage_bps/10000) for a BUY
    # (or best_bid × (1 - ...) for a SELL) and uses FAK so the unmatched
    # portion cancels rather than resting in the book. 50 bps = 0.5%.
    live_order_slippage_bps: int = _opt_int("LIVE_ORDER_SLIPPAGE_BPS", 50)
    max_position_per_market_usd: float = _opt_float("MAX_POSITION_PER_MARKET_USD", 500.0)
    max_daily_volume_usd: float = _opt_float("MAX_DAILY_VOLUME_USD", 1000.0)
    fetch_interval: float = _opt_int("FETCH_INTERVAL", 1) * 1.0  # seconds
    fetch_concurrency: int = max(1, _opt_int("FETCH_CONCURRENCY", 5))
    max_trade_age_hours: float = _opt_float("MAX_TRADE_AGE_HOURS", 1.0)
    max_price_drift_bps: int = _opt_int("MAX_PRICE_DRIFT_BPS", 300)
    max_spread_bps: int = _opt_int("MAX_SPREAD_BPS", 500)
    max_copies_per_market_side: int = _opt_int("MAX_COPIES_PER_MARKET_SIDE", 2)
    redeem_interval_hours: float = _opt_float("REDEEM_INTERVAL_HOURS", 0.5)
    # Paper-mode realization: in preview the on-chain redeemer is gated off, so
    # System-A copy positions would never realize. When enabled, the periodic
    # loop books realized P&L for resolved preview positions (and preview SELLs
    # book an early-exit P&L) so /pnl reflects a real paper track record.
    preview_realize_enabled: bool = _opt_bool("PREVIEW_REALIZE_ENABLED", True)
    trade_monitor_mode: str = _optional("TRADE_MONITOR_MODE", "data-api")

    # --- Copy-paper harness (Strategy 1b validation; PREVIEW-only, no orders) ---
    # Forward measurement of execution-realistic copy PnL on watchlist wallets.
    # Graduates a wallet to real capital only after positive net-of-drag PnL.
    # On by default: paper-only (places no real orders), so it's safe to run
    # everywhere. Set COPY_PAPER_ENABLED=false to stop it.
    copy_paper_enabled: bool = _opt_bool("COPY_PAPER_ENABLED", True)
    copy_paper_watchlist: str = _optional(
        "COPY_PAPER_WATCHLIST",
        str(Path(__file__).resolve().parent.parent / "data" / "copy_watchlist.json"),
    )
    copy_paper_ledger: str = _optional(
        "COPY_PAPER_LEDGER",
        str(Path(__file__).resolve().parent.parent / "data" / "copy_paper_ledger.jsonl"),
    )
    copy_paper_max_usd: float = _opt_float("COPY_PAPER_MAX_USD", 50.0)
    copy_paper_copy_pct: float = _opt_float("COPY_PAPER_COPY_PCT", 1.0)
    copy_paper_max_slippage_bps: int = _opt_int("COPY_PAPER_MAX_SLIPPAGE_BPS", 200)
    copy_paper_max_age_s: float = _opt_float("COPY_PAPER_MAX_AGE_S", 21600.0)
    copy_paper_min_usd: float = _opt_float("COPY_PAPER_MIN_USD", 500.0)
    copy_paper_interval_s: int = _opt_int("COPY_PAPER_INTERVAL_S", 120)

    # --- Wallet discovery (continuously hunts copyable wallets -> paper) ---
    # Runs the discovery funnel on a schedule; pings Telegram on each new
    # qualifier and adds it to the paper watchlist. Never touches live capital.
    # On by default: discovery only writes a paper watchlist + Telegram pings,
    # never touches live capital. Set WALLET_DISCOVERY_ENABLED=false to stop it.
    wallet_discovery_enabled: bool = _opt_bool("WALLET_DISCOVERY_ENABLED", True)
    # Wide insider sweep: scan a large universe (take whatever the trade feed
    # yields up to this cap) on a slow multi-day cadence. The funnel paces its
    # requests (WALLET_DISCOVERY_PAGE_PAUSE_S / _BATCH_PAUSE_S) to stay under the
    # 429 ceiling and streams the scoring in chunks so RAM stays bounded.
    wallet_discovery_interval_s: int = _opt_int("WALLET_DISCOVERY_INTERVAL_S", 86400)  # 1d
    wallet_discovery_universe: int = _opt_int("WALLET_DISCOVERY_UNIVERSE", 200000)
    wallet_discovery_skill_pool: int = _opt_int("WALLET_DISCOVERY_SKILL_POOL", 40)
    wallet_discovery_cap: int = _opt_int("WALLET_DISCOVERY_CAP", 25)
    wallet_discovery_min_capture_cents: float = _opt_float("WALLET_DISCOVERY_MIN_CAPTURE_CENTS", 1.5)
    wallet_discovery_min_tstat: float = _opt_float("WALLET_DISCOVERY_MIN_TSTAT", 10.0)
    wallet_discovery_drop_capture_cents: float = _opt_float("WALLET_DISCOVERY_DROP_CAPTURE_CENTS", 1.0)
    wallet_discovery_auto_remove: bool = _opt_bool("WALLET_DISCOVERY_AUTO_REMOVE", True)
    wallet_discovery_category: str = _optional("WALLET_DISCOVERY_CATEGORY", "ALL")
    # Gated Claude second-opinion (Strategy 1c): for the top-N statistically
    # qualified wallets, ask Claude to vet a compact dossier. Alert-only, never
    # auto-trades; off by default and needs ANTHROPIC_API_KEY.
    wallet_discovery_llm_review_enabled: bool = _opt_bool("WALLET_DISCOVERY_LLM_REVIEW_ENABLED", False)
    wallet_discovery_llm_review_top_n: int = _opt_int("WALLET_DISCOVERY_LLM_REVIEW_TOP_N", 5)
    wallet_discovery_llm_model: str = _optional("WALLET_DISCOVERY_LLM_MODEL", "claude-opus-4-8")
    # Independent strategy theories that may qualify a wallet (OR'd). Backtest-
    # supported default; add 1a/1e/1j to experiment. See research/THEORY_FINDINGS.md.
    wallet_discovery_theories: str = _optional("WALLET_DISCOVERY_THEORIES", "1b,1c,1d,1f,1g,1h,1i")
    # Activity-cache TTL: set ABOVE the sweep interval so a returning wallet is
    # served from cache instead of re-fetched (TTL < interval would expire every
    # time and never hit). 30h vs a 24h sweep. prune_cache deletes files older
    # than this, so it doubles as the disk-eviction horizon. Universe defaults to
    # wallets active in the last WALLET_DISCOVERY_UNIVERSE_WINDOW_S (24h); set
    # WALLET_DISCOVERY_EXPAND_FILTERS=true for a wider (BUY/SELL × taker) sweep.
    wallet_discovery_activity_ttl_s: int = _opt_int("WALLET_DISCOVERY_ACTIVITY_TTL_S", 108000)  # 30h
    wallet_discovery_cache_dir: str = _optional(
        "WALLET_DISCOVERY_CACHE_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "wcache"),
    )
    wallet_discovery_state: str = _optional(
        "WALLET_DISCOVERY_STATE",
        str(Path(__file__).resolve().parent.parent / "data" / "discovery_state.json"),
    )

    # --- APIs ---
    clob_api_url: str = _optional("CLOB_API_URL", "https://clob.polymarket.com")
    data_api_url: str = _optional("DATA_API_URL", "https://data-api.polymarket.com")
    rpc_url: str = _optional("RPC_URL", "https://polygon-rpc.com")
    etherscan_api_key: str = _optional("ETHERSCAN_API_KEY", "")
    chain_id: int = 137

    # --- Directories ---
    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")
    cache_dir: str = str(Path(__file__).resolve().parent.parent / "cache")
    results_dir: str = str(Path(__file__).resolve().parent.parent / "results")
    logs_dir: str = str(Path(__file__).resolve().parent.parent / "logs")


CONFIG = Config()
