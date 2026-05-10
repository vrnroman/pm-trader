"""Thin HTTP client to the claude-runner on the claude-agent VM.

The runner exposes:
  POST   /tasks                   {prompt, chat_id}    → {id, status, ...}
  GET    /tasks                                        → [task,...]
  GET    /tasks/<id>?tail=N                            → {..., log_tail:[...]}
  POST   /tasks/<id>/reply        {text}               → {ok}
  POST   /tasks/<id>/cancel                            → {ok}
  GET    /healthz                                      → {ok, current}

All requests carry an X-Runner-Secret header.
"""
from __future__ import annotations

from typing import Optional

import requests

from src.config import CONFIG


def _enabled() -> bool:
    return bool(CONFIG.runner_url) and bool(CONFIG.runner_shared_secret)


def _headers() -> dict:
    return {"X-Runner-Secret": CONFIG.runner_shared_secret}


def health() -> Optional[dict]:
    if not _enabled():
        return None
    r = requests.get(f"{CONFIG.runner_url}/healthz", headers=_headers(), timeout=5)
    r.raise_for_status()
    return r.json()


def create_task(prompt: str, chat_id: str) -> dict:
    r = requests.post(
        f"{CONFIG.runner_url}/tasks",
        json={"prompt": prompt, "chat_id": chat_id},
        headers=_headers(),
        timeout=15,
    )
    if r.status_code == 409:
        raise RuntimeError(r.json().get("detail", "another task is active"))
    r.raise_for_status()
    return r.json()


def list_tasks() -> list[dict]:
    r = requests.get(f"{CONFIG.runner_url}/tasks", headers=_headers(), timeout=5)
    r.raise_for_status()
    return r.json()


def get_task(task_id: str, tail: int = 20) -> Optional[dict]:
    r = requests.get(
        f"{CONFIG.runner_url}/tasks/{task_id}",
        params={"tail": tail},
        headers=_headers(),
        timeout=5,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def reply(task_id: str, text: str) -> bool:
    r = requests.post(
        f"{CONFIG.runner_url}/tasks/{task_id}/reply",
        json={"text": text},
        headers=_headers(),
        timeout=10,
    )
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return True


def cancel(task_id: str) -> bool:
    r = requests.post(
        f"{CONFIG.runner_url}/tasks/{task_id}/cancel",
        headers=_headers(),
        timeout=15,
    )
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return True


def current_task_id() -> Optional[str]:
    """Return the id of the currently active task, or None."""
    h = health()
    if not h:
        return None
    return h.get("current")
