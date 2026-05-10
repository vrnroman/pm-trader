FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-deploy gates: lint (F821 undefined names) + smoke (import every
# production module, including lazy imports inside helper functions).
# This catches the class of bug that took the bot down on 2026-05-10
# (latent NameErrors / ImportErrors in cold paths). Build fails here →
# deploy script never ships a broken image.
RUN pip install --no-cache-dir ruff && \
    ruff check --select F821 src main.py && \
    python -c "\
import main; \
from src.copy_trading import runner, trade_executor, inventory, clob_client, order_executor; \
from src.tennis import tennis_arb, order_placer, paper_book; \
from src import telegram_bot, runtime_state; \
from src.copy_trading.trade_executor import _trade_store, _trade_queue, _inventory, _risk_manager, _tiered_risk, _strategy_config; \
_trade_store(); _trade_queue(); _inventory(); _risk_manager(); _tiered_risk(); _strategy_config(); \
print('SMOKE OK')" && \
    pip uninstall -y ruff

RUN mkdir -p data cache results logs

RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]
