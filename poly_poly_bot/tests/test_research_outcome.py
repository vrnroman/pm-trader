"""/research decides what reaches the owner's phone, never what the bot does."""

from src import telegram_bot


def test_held_research_push_is_muted_not_failed(monkeypatch):
    monkeypatch.setattr(telegram_bot, "research_enabled", lambda: False)
    assert telegram_bot.research_outcome(False) == telegram_bot.MUTED
    assert telegram_bot.research_outcome(True) is True


def test_failed_send_with_research_on_is_still_a_failure(monkeypatch):
    monkeypatch.setattr(telegram_bot, "research_enabled", lambda: True)
    assert telegram_bot.research_outcome(False) is False
    assert telegram_bot.research_outcome(True) is True
