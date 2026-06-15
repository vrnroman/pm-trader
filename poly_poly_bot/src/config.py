"""Unified configuration for all three strategies."""

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
_strategy2_enabled = _opt_bool("STRATEGY2_ENABLED", False)
_strategy3_enabled = _opt_bool("STRATEGY3_ENABLED", False)

_user_addresses = _load_user_addresses()

# Validate proxy wallet only when Strategy 1 is enabled
_proxy_wallet = ""
if _strategy1_enabled and os.environ.get("PROXY_WALLET", "").strip():
    _proxy_wallet = validate_address(_required("PROXY_WALLET"), "PROXY_WALLET")


class Config:
    """Unified configuration for all strategies."""

    # --- Strategy toggles ---
    strategy1_enabled: bool = _strategy1_enabled
    strategy2_enabled: bool = _strategy2_enabled
    strategy3_enabled: bool = _strategy3_enabled

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
    trade_monitor_mode: str = _optional("TRADE_MONITOR_MODE", "data-api")

    # --- Strategy 2: Weather Betting ---
    cities_to_bet: str = _optional("CITIES_TO_BET", "nyc,chicago,denver,dallas")
    days_in_advance: int = _opt_int("DAYS_IN_ADVANCE", 4)
    min_edge: float = _opt_float("MIN_EDGE", 0.10)
    bet_size: float = _opt_float("BET_SIZE", 10.0)
    max_bets_per_city: int = _opt_int("MAX_BETS_PER_CITY", 2)
    schedule_hour_sgt: int = _opt_int("SCHEDULE_HOUR_SGT", 15)
    schedule_minute_sgt: int = _opt_int("SCHEDULE_MINUTE_SGT", 0)

    # --- Strategy 3: Tennis Arb (Smarkets-only) ---
    tennis_min_divergence: float = _opt_float("TENNIS_MIN_DIVERGENCE", 0.06)
    # After Gamma's edge clears tennis_min_divergence, we refetch the live
    # CLOB ask (which is what we'd actually pay) and recompute the edge.
    # If the live edge is still ≥ this floor, we fire — otherwise the
    # signal is dropped because Gamma's last-trade price was stale.
    tennis_revalidation_min_divergence: float = _opt_float(
        "TENNIS_REVALIDATION_MIN_DIVERGENCE", 0.06
    )
    tennis_max_bet_size: float = _opt_float("TENNIS_MAX_BET_SIZE", 165.0)
    tennis_kelly_fraction: float = _opt_float("TENNIS_KELLY_FRACTION", 0.3)
    tennis_scan_interval: int = _opt_int("TENNIS_SCAN_INTERVAL", 20)
    # Per-scan discovery-cache path (Batch 3). When True, the scanner reads
    # the pre-warmed PM ↔ Smarkets cache and prices off live CLOB books in
    # one batched call, eliminating per-scan Gamma and the revalidation
    # dance. Flip to False to fall back to the legacy Gamma-per-scan path
    # without redeploying.
    tennis_use_discovery_cache: bool = _opt_bool("TENNIS_USE_DISCOVERY_CACHE", True)
    tennis_tournaments: str = _optional("TENNIS_TOURNAMENTS", "ATP,WTA")
    tennis_min_polymarket_volume: float = _opt_float("TENNIS_MIN_POLYMARKET_VOLUME", 20000)
    tennis_min_polymarket_liquidity: float = _opt_float("TENNIS_MIN_POLYMARKET_LIQUIDITY", 5000)
    tennis_take_profit_ratio: float = _opt_float("TENNIS_TAKE_PROFIT_RATIO", 3.0)

    # --- Strategy 3: dual-sharp REST stream + RTDS (event-driven path) ---
    # Sharp provider selection. Allowed: betsapi | pinnacle | betsapi+pinnacle
    # | smarkets | betsapi+pinnacle+smarkets. Default is dual-sharp so we
    # collect a week of BetsAPI-vs-Pinnacle lead-ms telemetry before flipping
    # to a single-provider primary (rollout §12 step 7).
    tennis_sharp_provider: str = _optional("TENNIS_SHARP_PROVIDER", "betsapi+pinnacle")
    # BetsAPI (primary REST 1Hz-per-event poller).
    betsapi_token: str = _optional("BETSAPI_TOKEN", "")
    betsapi_base_url: str = _optional("BETSAPI_BASE_URL", "https://api.b365api.com")
    betsapi_poll_hz_per_event: float = _opt_float("BETSAPI_POLL_HZ_PER_EVENT", 1.0)
    betsapi_primary_book: str = _optional("BETSAPI_PRIMARY_BOOK", "pinnacle")
    # RapidAPI Pinnacle Odds (secondary REST ?since= delta poller).
    pinnacle_rapidapi_key: str = _optional("PINNACLE_RAPIDAPI_KEY", "")
    pinnacle_rapidapi_host: str = _optional(
        "PINNACLE_RAPIDAPI_HOST", "pinnacle-odds.p.rapidapi.com"
    )
    pinnacle_poll_interval_ms: float = _opt_float("PINNACLE_POLL_INTERVAL_MS", 1000.0)
    # Event-driven eval gates.
    tennis_heartbeat_interval: float = _opt_float("TENNIS_HEARTBEAT_INTERVAL", 30.0)
    # PM staleness gate: only fire if the sharp event is at least this many ms
    # newer than the PM book we'd trade against (proves PM hasn't repainted).
    min_pm_lag_ms: float = _opt_float("MIN_PM_LAG_MS", 100.0)
    # Polymarket RTDS WebSocket book mirror. Non-negotiable kill switch: flip
    # false to revert every PM read to the existing REST path.
    polymarket_use_rtds: bool = _opt_bool("POLYMARKET_USE_RTDS", True)
    polymarket_rtds_ws_url: str = _optional("POLYMARKET_RTDS_WS_URL", "")

    # --- Copy-paper harness (Strategy 1b validation; PREVIEW-only, no orders) ---
    # Forward measurement of execution-realistic copy PnL on watchlist wallets.
    # Graduates a wallet to real capital only after positive net-of-drag PnL.
    copy_paper_enabled: bool = _opt_bool("COPY_PAPER_ENABLED", False)
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
    wallet_discovery_enabled: bool = _opt_bool("WALLET_DISCOVERY_ENABLED", False)
    # Wide insider sweep: scan a large universe (take whatever the trade feed
    # yields up to this cap) on a slow multi-day cadence. The funnel paces its
    # requests (WALLET_DISCOVERY_PAGE_PAUSE_S / _BATCH_PAUSE_S) to stay under the
    # 429 ceiling and streams the scoring in chunks so RAM stays bounded.
    wallet_discovery_interval_s: int = _opt_int("WALLET_DISCOVERY_INTERVAL_S", 345600)  # 4d
    wallet_discovery_universe: int = _opt_int("WALLET_DISCOVERY_UNIVERSE", 200000)
    wallet_discovery_skill_pool: int = _opt_int("WALLET_DISCOVERY_SKILL_POOL", 40)
    wallet_discovery_cap: int = _opt_int("WALLET_DISCOVERY_CAP", 25)
    wallet_discovery_min_capture_cents: float = _opt_float("WALLET_DISCOVERY_MIN_CAPTURE_CENTS", 1.5)
    wallet_discovery_min_tstat: float = _opt_float("WALLET_DISCOVERY_MIN_TSTAT", 10.0)
    wallet_discovery_drop_capture_cents: float = _opt_float("WALLET_DISCOVERY_DROP_CAPTURE_CENTS", 1.0)
    wallet_discovery_auto_remove: bool = _opt_bool("WALLET_DISCOVERY_AUTO_REMOVE", True)
    wallet_discovery_category: str = _optional("WALLET_DISCOVERY_CATEGORY", "ALL")
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
