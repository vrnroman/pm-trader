// Data API polling source — wraps existing fetchAllTraderActivities with source interface

import { TradeSource } from "./trade-source";
import { fetchAllTraderActivities } from "./trade-monitor";
import { isSeenTrade, isMaxRetries } from "./trade-store";
import { enqueueTrade } from "./trade-queue";
import { isMarketEnded } from "./market-cache";
import { CONFIG } from "./config";
import { logger } from "./logger";
import { errorMessage } from "./types";
import { sleep } from "./utils";
import { telegram } from "./telegram-notifier";

export class DataApiSource implements TradeSource {
  name = "data-api";
  private running = false;

  async start(): Promise<void> {
    this.running = true;
    const CIRCUIT_BREAKER_THRESHOLD = 10;
    let consecutiveFailures = 0;
    let circuitBreakerAlerted = false;

    while (this.running) {
      try {
        const trades = await fetchAllTraderActivities();
        const now = Date.now();
        const maxAgeMs = CONFIG.maxTradeAgeHours * 60 * 60 * 1000;
        const newTrades = trades.filter(t => {
          if (isSeenTrade(t.id) || isMaxRetries(t.id)) return false;
          // Trade age gate: skip trades older than MAX_TRADE_AGE_HOURS.
          // Defense-in-depth against cursor resets after bot restart causing
          // old trades to be re-fetched from the Data API.
          const tradeTime = new Date(t.timestamp).getTime();
          if (isNaN(tradeTime) || now - tradeTime > maxAgeMs) return false;
          return true;
        });
        for (const trade of newTrades) {
          // Skip trades on markets that have already resolved/ended
          if (trade.conditionId) {
            try {
              if (await isMarketEnded(trade.conditionId)) {
                logger.debug(`Skipping trade on ended market: "${trade.market}"`);
                continue;
              }
            } catch { /* non-critical — proceed with enqueue */ }
          }
          enqueueTrade(trade, new Date(trade.timestamp).getTime(), "data-api");
        }
        consecutiveFailures = 0;
        circuitBreakerAlerted = false;
      } catch (err: unknown) {
        consecutiveFailures++;
        logger.error(`Data API error (${consecutiveFailures}x): ${errorMessage(err)}`);
        if (consecutiveFailures >= CIRCUIT_BREAKER_THRESHOLD && !circuitBreakerAlerted) {
          circuitBreakerAlerted = true;
          telegram.botError(`Data API circuit breaker: ${consecutiveFailures} failures. Last: ${errorMessage(err)}`);
        }
      }

      const backoff = consecutiveFailures > 0
        ? Math.min(CONFIG.fetchInterval * Math.pow(2, Math.min(consecutiveFailures, 6)), 300_000)
        : CONFIG.fetchInterval;
      await sleep(backoff);
    }
  }

  stop(): void {
    this.running = false;
  }
}
