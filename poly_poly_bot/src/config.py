"""Configuration for the news bot.

The copy-trading bot this repo used to run was removed on 2026-10-27 (the
owner: "delete whatever related to copy-bot"); what is left is the news
bot's own knobs (read where they are used, under NEWS_*), the Telegram chat,
and the directories. Real money is not wired: nothing here can sign an order.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _optional(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


def _opt_bool(name: str, fallback: bool) -> bool:
    """Only the literal "true" is true: NEWS_MODE=1 once read as false and
    started the wrong bot (2026-10-25)."""
    v = os.environ.get(name, "").strip()
    if not v:
        return fallback
    return v.lower() == "true"


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str = _optional("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = _optional("TELEGRAM_CHAT_ID", "")
    data_dir: str = _optional("DATA_DIR", str(_ROOT / "data"))
    logs_dir: str = str(_ROOT / "logs")


CONFIG = Config()
