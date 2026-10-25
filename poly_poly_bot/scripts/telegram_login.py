#!/usr/bin/env python3
"""One-time, interactive: log the owner's Telegram account in through the
client API and print the session string the news bot needs.

Run this ON YOUR MAC, once (never on the VM; the VM only needs the result):

    cd poly_poly_bot
    .venv/bin/python -m scripts.telegram_login

Where the two credentials come from: https://my.telegram.org -> log in with
your phone number -> "API development tools" -> create an app (any name and
short name, platform "Other"). The page shows `App api_id` (a number) and
`App api_hash` (32 hex chars). They identify the application, not you; the
login below is what ties them to your account.

What the script does: asks for the phone number, the code Telegram sends to
your other devices (NOT an SMS, usually), and the two-step password if the
account has one; then prints a Telethon StringSession and the exact three
lines to add to the deployment's ENV_FILE secret. The session is held in
memory only and never written to disk by this script.

THE SESSION STRING IS A LOGIN. Anyone holding it reads your chats and can
send as you until you revoke it (Telegram -> Settings -> Devices -> that
session -> Terminate). Treat it exactly like the account password: paste it
into the secret, then clear the terminal scrollback.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys


def _ask(prompt: str, secret: bool = False) -> str:
    try:
        return (getpass.getpass(prompt) if secret else input(prompt)).strip()
    except EOFError:
        return ""


def _credentials() -> tuple[int, str]:
    raw_id = (os.environ.get("TELEGRAM_API_ID") or "").strip() or _ask("TELEGRAM_API_ID (number from my.telegram.org): ")
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip() or _ask("TELEGRAM_API_HASH: ", secret=True)
    try:
        api_id = int(raw_id)
    except ValueError:
        sys.exit(f"api_id must be a number, got {raw_id!r}")
    if len(api_hash) < 16:
        sys.exit("api_hash looks too short; copy it from the API development tools page")
    return api_id, api_hash


async def _login(api_id: int, api_hash: str) -> str:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), api_id, api_hash)
    # Interactive: phone, code (and the 2FA password if the account has one).
    await client.start(phone=lambda: _ask("Phone number (international, e.g. +81...): "),
                       password=lambda: _ask("Two-step verification password: ", secret=True),
                       code_callback=lambda: _ask("Login code Telegram just sent you: "))
    me = await client.get_me()
    session = client.session.save()
    await client.disconnect()
    who = f"@{me.username}" if getattr(me, "username", None) else (getattr(me, "first_name", "") or "this account")
    print(f"\nLogged in as {who}. The session below is the login; keep it like a password.\n", file=sys.stderr)
    return session


def main() -> int:
    try:
        import telethon  # noqa: F401
    except ImportError:
        print("telethon is not installed in this interpreter: `.venv/bin/python -m pip install 'telethon>=1.36'`",
              file=sys.stderr)
        return 2
    api_id, api_hash = _credentials()
    session = asyncio.run(_login(api_id, api_hash))
    print("Add these three lines to the repository's ENV_FILE secret"
          " (GitHub -> Settings -> Secrets and variables -> Actions -> ENV_FILE), then push or re-run Deploy:\n")
    print(f"TELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print(f"TELEGRAM_USER_SESSION={session}")
    print("\nOptional: NEWS_TGM_CHANNELS=chan1,chan2 for channels beyond the roster's twelve.", file=sys.stderr)
    print("Nothing was written to disk. Clear this terminal's scrollback when the secret is saved.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
