"""newsbot: a news-driven Polymarket paper trader (see DESIGN.md).

This package is a leaf of the repo: it imports ``src.logger`` and nothing
else from the copy bot, so the sources layer can be tested on saved fixtures
with no network and no bot state.
"""
