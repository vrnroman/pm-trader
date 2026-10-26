# Pinned to bookworm: the bare `python:3.12-slim` tag rolled to Debian 13
# (trixie) on 2026-07-27, whose own nodejs 20 package shadowed the nodesource
# repo and splits npm into a separate package — the build died at
# `npm: not found`. Pin the distro so upstream tag drift can't break the build.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# Node + Claude Code CLI. The news judge shells out to `claude -p`, which runs
# on the operator's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN, from
# `claude setup-token`) rather than an ANTHROPIC_API_KEY. Without the token
# nothing is judged and nothing is bought; the brief says so.
# Node comes from the official pinned tarball, NOT the nodesource setup script:
# deb.nodesource.com/setup_22.x started returning 403 on 2026-07-27, and the
# old pipe (`curl | bash`, no pipefail) turned that into a silent no-op — apt
# then installed the distro nodejs, which splits npm out, and the build died at
# `npm: not found`. Pinned v22 LTS; bump deliberately.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils \
    && curl -fsSL https://nodejs.org/dist/v22.17.0/node-v22.17.0-linux-x64.tar.xz -o /tmp/node-v22.17.0-linux-x64.tar.xz \
    && curl -fsSL https://nodejs.org/dist/v22.17.0/SHASUMS256.txt -o /tmp/SHASUMS256.txt \
    && (cd /tmp && grep "node-v22.17.0-linux-x64.tar.xz$" SHASUMS256.txt | sha256sum -c -) \
    && tar -xJf /tmp/node-v22.17.0-linux-x64.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node-v22.17.0-linux-x64.tar.xz /tmp/SHASUMS256.txt \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

# glibc malloc tuning (kept from the copy bot, which used numpy/pandas/web3). By default glibc spins up to 8*ncpu per-thread malloc arenas, each of
# which hoards freed memory and never returns it to the OS — so RSS balloons
# far above live-object size (measured 2026-06-15: ~1.44GB anonymous heap vs a
# ~210MB code floor). Capping arenas + lowering the trim threshold reclaims
# freed heap, cutting steady-state and post-discovery-sweep RSS substantially.
ENV MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=131072

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
from src import telegram_bot; \
from src.newsbot import runner, judge, paper, pnl, fees, resolve, leads, index; \
from src.newsbot.sources import poller, rss, telegram_web, telegram_mtproto, x_cookies, bluesky; \
from src.newsbot.tape import livedata, clob_ws, jumps; \
print('SMOKE OK')" && \
    pip uninstall -y ruff

RUN mkdir -p data cache results logs

RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]
