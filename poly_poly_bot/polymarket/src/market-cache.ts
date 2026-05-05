// Market metadata cache — maps tokenId to market name/conditionId/outcome
// Used by on-chain source to enrich raw OrderFilled events with human-readable data.
// Cache is immutable (market metadata never changes) — persisted to disk, grows only.

import fs from "fs";
import path from "path";
import axios from "axios";
import { CONFIG } from "./config";
import { logger } from "./logger";
import { errorMessage } from "./types";

export interface MarketMeta {
  conditionId: string;
  market: string;       // human-readable title
  outcome: string;      // "Yes" / "No" / outcome name
  tokenId: string;
}

const DATA_DIR = path.resolve(process.cwd(), "data");
const CACHE_FILE = path.join(DATA_DIR, "market-cache.json");

// In-memory cache: tokenId → MarketMeta
const cache = new Map<string, MarketMeta>();

// Load disk cache on module init
function loadCache(): void {
  try {
    if (fs.existsSync(CACHE_FILE)) {
      const data: MarketMeta[] = JSON.parse(fs.readFileSync(CACHE_FILE, "utf8"));
      for (const m of data) cache.set(m.tokenId, m);
      logger.debug(`Market cache loaded: ${cache.size} entries`);
    }
  } catch { /* corrupted — start fresh */ }
}

function saveCache(): void {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  const data = JSON.stringify([...cache.values()]);
  const tmp = CACHE_FILE + ".tmp";
  fs.writeFileSync(tmp, data);
  try {
    fs.renameSync(tmp, CACHE_FILE);
  } catch {
    fs.writeFileSync(CACHE_FILE, data);
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
  }
}

loadCache();

/** Look up market metadata for a tokenId. Fetches from CLOB API on cache miss. Returns null on failure. */
export async function getMarketMeta(tokenId: string): Promise<MarketMeta | null> {
  const cached = cache.get(tokenId);
  if (cached) return cached;

  try {
    // CLOB API supports lookup by token asset ID
    const res = await axios.get(`${CONFIG.clobApiUrl}/markets`, {
      params: { asset_id: tokenId },
      timeout: 10000,
    });

    // Response is a single market object or array
    const market = Array.isArray(res.data) ? res.data[0] : res.data;
    if (!market || !market.condition_id) return null;

    // Find which outcome this token belongs to
    const tokens = market.tokens || [];
    const tokenEntry = tokens.find((t: { token_id?: string }) => t.token_id === tokenId);
    const outcome = tokenEntry?.outcome || "";

    const meta: MarketMeta = {
      conditionId: market.condition_id,
      market: market.question || market.title || "unknown",
      outcome,
      tokenId,
    };

    cache.set(tokenId, meta);
    saveCache();
    return meta;
  } catch (err: unknown) {
    logger.warn(`Market cache miss for tokenId ${tokenId}: ${errorMessage(err)}`);
    return null;
  }
}

/** Pre-warm cache for a batch of token IDs (skips already cached). */
export async function warmCache(tokenIds: string[]): Promise<void> {
  const uncached = tokenIds.filter(id => !cache.has(id));
  for (const id of uncached) {
    await getMarketMeta(id);
  }
}

// ---------------------------------------------------------------------------
// Market end-date / resolution cache
// ---------------------------------------------------------------------------

const END_DATE_CACHE_FILE = path.join(DATA_DIR, "market-end-dates.json");

const endDateCache = new Map<string, string>();

function loadEndDates(): void {
  try {
    if (fs.existsSync(END_DATE_CACHE_FILE)) {
      const data = JSON.parse(fs.readFileSync(END_DATE_CACHE_FILE, "utf8"));
      for (const [k, v] of Object.entries(data)) {
        endDateCache.set(k, v as string);
      }
    }
  } catch { /* corrupted — start fresh */ }
}

function saveEndDates(): void {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  const obj: Record<string, string> = {};
  for (const [k, v] of endDateCache) obj[k] = v;
  const tmp = END_DATE_CACHE_FILE + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(obj));
  try { fs.renameSync(tmp, END_DATE_CACHE_FILE); } catch {
    fs.writeFileSync(END_DATE_CACHE_FILE, JSON.stringify(obj));
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
  }
}

loadEndDates();

/** Check if a market's end date is in the past (async, caches results). Returns false when unknown. */
export async function isMarketEnded(conditionId: string): Promise<boolean> {
  if (!conditionId) return false;
  const key = conditionId.toLowerCase();

  if (!endDateCache.has(key)) {
    try {
      const res = await axios.get(`${CONFIG.clobApiUrl}/markets/${conditionId}`, { timeout: 5000 });
      const data = res.data;
      const endDate = data?.end_date_iso || data?.end_date || "";
      endDateCache.set(key, endDate);
      saveEndDates();
    } catch {
      endDateCache.set(key, "");
      saveEndDates();
    }
  }

  const raw = endDateCache.get(key) || "";
  if (!raw) return false;

  try {
    return new Date(raw).getTime() < Date.now();
  } catch {
    return false;
  }
}
