#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────
# Load project ID from .env (or use default)
if [ -f .env ]; then
    GCP_PROJECT_ID=$(grep -E '^GCP_PROJECT_ID=' .env | cut -d= -f2 | tr -d '"' || true)
fi
GCP_PROJECT_ID="${GCP_PROJECT_ID:-roman-vm}"

INSTANCE="poly-poly-bot"
ZONE="asia-northeast1-a"   # Tokyo, Japan
MACHINE="e2-small"          # 2 vCPU (shared/burstable), 2GB RAM
IMAGE_TAG="poly-poly-bot:latest"
IMAGE_TAR="/tmp/poly-poly-bot-image.tar.gz"

# Build host vs run host:
#   The image is built HERE (a fast, resourceful machine — the GitHub
#   Actions runner, native amd64) and the finished image is shipped to the
#   VM, which only `docker load`s and runs it. The e2-small never compiles
#   pandas/scipy/web3 again, so deploys are minutes not 40+ min, and a
#   CPU-starved VM can't wedge the build (which on 2026-06-15 stopped the
#   old container, ran a 40-min build, and left the bot down throughout).

# SSH transport. In CI (GitHub Actions) the runner has no route to the VM's
# SSH port, so set DEPLOY_USE_IAP=1 to tunnel ssh/scp through IAP — no public
# IP or open-to-the-world firewall rule required. Local deploys leave it unset
# and connect directly, exactly as before.
SSH_FLAGS=()
if [ "${DEPLOY_USE_IAP:-0}" = "1" ]; then
    SSH_FLAGS=(--tunnel-through-iap)
    echo "  SSH: tunneling through IAP"
fi

# The app lives in ~/app of the SSH login user. Locally you connect as your own
# gcloud identity; in CI the service account is a *different* Linux user with a
# *different* home, so it would deploy into the wrong place and miss the
# existing container + data volume. Set DEPLOY_SSH_USER to the username whose
# ~/app holds the current deployment so CI lands in the same home. Unset =
# connect as the caller's default user (local behaviour, unchanged).
TARGET="$INSTANCE"
if [ -n "${DEPLOY_SSH_USER:-}" ]; then
    TARGET="${DEPLOY_SSH_USER}@${INSTANCE}"
    echo "  SSH user: $DEPLOY_SSH_USER"
fi

echo "=== Poly Poly Bot Deployment (build-here → load-on-VM) ==="
echo "  Project: $GCP_PROJECT_ID"
echo "  Instance: $INSTANCE"
echo "  Zone: $ZONE"
echo "  Machine: $MACHINE"
echo ""

# ─── Step 0: Docker required on THIS host ────────────────────────
# We build the image locally now. macOS arm64 has no docker by default —
# the canonical deploy path is `git push origin main` (CI builds + ships).
# To deploy by hand from a docker-equipped host, that host must have docker.
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker not found on this host."
    echo "   This deploy builds the image here and ships it to the VM, so the"
    echo "   build host needs docker. Either push to main (CI builds it for you)"
    echo "   or install a runtime (e.g. macOS: 'brew install colima docker && colima start')."
    exit 1
fi

# ─── Step 1: Ensure VM exists ────────────────────────────────────
if ! gcloud compute instances describe "$INSTANCE" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE" &>/dev/null; then
    echo "[1/5] Creating VM..."
    gcloud compute instances create "$INSTANCE" \
        --project="$GCP_PROJECT_ID" \
        --zone="$ZONE" \
        --machine-type="$MACHINE" \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --boot-disk-size=20GB \
        --metadata=startup-script='#!/bin/bash
            apt-get update
            apt-get install -y docker.io docker-compose-v2
            systemctl enable docker
            systemctl start docker
            usermod -aG docker $(whoami)
        '
    echo "  Waiting 30s for startup..."
    sleep 30
else
    echo "[1/5] VM exists, reusing."
fi

# ─── Step 2: Build image HERE (native amd64 on the runner) ───────
# The Dockerfile's RUN steps run the lint (ruff F821) + import smoke gate, so
# a broken image fails the build before it's ever shipped — same gate as
# before, just on a fast host. --platform linux/amd64 is a no-op on the amd64
# runner and forces a VM-compatible image if built on an arm64 Mac.
# .dockerignore keeps .env and the git/cache/data dirs out of the image.
echo "[2/5] Building image on $(uname -m) host: $IMAGE_TAG ..."
DOCKER_BUILDKIT=1 docker build --platform linux/amd64 -t "$IMAGE_TAG" .

echo "  Saving + compressing image..."
docker save "$IMAGE_TAG" | gzip > "$IMAGE_TAR"
echo "  Image archive: $(du -h "$IMAGE_TAR" | cut -f1)"

# ─── Step 3: Upload image + .env ─────────────────────────────────
echo "[3/5] Uploading image to VM (IAP)..."
gcloud compute ssh "$TARGET" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE" "${SSH_FLAGS[@]}" \
    --command='mkdir -p ~/app'
gcloud compute scp "${SSH_FLAGS[@]}" "$IMAGE_TAR" "$TARGET:~/poly-poly-bot-image.tar.gz" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE"
gcloud compute scp "${SSH_FLAGS[@]}" .env "$TARGET:~/app/.env" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE"

# ─── Step 4: Load & Run on VM (NO build) ─────────────────────────
echo "[4/5] Loading & starting on VM..."
gcloud compute ssh "$TARGET" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE" "${SSH_FLAGS[@]}" \
    --command='
        set -e
        cd ~/app

        # Preserve data across deployments
        mkdir -p data cache results logs

        # Force preview mode on every deploy: drop the persisted
        # preview/live toggle so the bot boots with PREVIEW_MODE from
        # .env. Telegram /live 3 CONFIRM re-creates the file as needed.
        rm -f data/runtime_state.json

        # Load the prebuilt image (seconds, no compiling)
        echo "Loading image..."
        docker load < ~/poly-poly-bot-image.tar.gz
        rm -f ~/poly-poly-bot-image.tar.gz

        # Swap container: stop old, run new. The old container stays up until
        # right before the new one starts, so downtime is the few seconds of
        # load+restart — not a multi-minute build.
        docker stop poly-poly-bot 2>/dev/null || true
        docker rm poly-poly-bot 2>/dev/null || true

        docker run -d \
            --name poly-poly-bot \
            --restart unless-stopped \
            --env-file .env \
            -v ~/app/data:/app/data \
            -v ~/app/cache:/app/cache \
            -v ~/app/results:/app/results \
            -v ~/app/logs:/app/logs \
            poly-poly-bot:latest

        echo "Container started:"
        docker ps --filter name=poly-poly-bot --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

        # Reclaim space: the previous image is now untagged (<none>). Without
        # this the 20GB boot disk fills over time. Only touches dangling
        # images + stopped containers; the current tagged image stays.
        echo "Pruning dangling images and stopped containers..."
        docker image prune -f
        docker container prune -f
    '

# ─── Step 5: Verify ──────────────────────────────────────────────
echo "[5/5] Verifying..."
sleep 3
gcloud compute ssh "$TARGET" \
    --project="$GCP_PROJECT_ID" --zone="$ZONE" "${SSH_FLAGS[@]}" \
    --command='docker logs poly-poly-bot --tail 20'

echo ""
echo "=== Deployment complete ==="
echo "  Monitor: gcloud compute ssh $INSTANCE --zone=$ZONE --tunnel-through-iap --command='docker logs -f poly-poly-bot'"
echo "  Stop:    gcloud compute ssh $INSTANCE --zone=$ZONE --tunnel-through-iap --command='docker stop poly-poly-bot'"
echo "  Logs:    gcloud compute ssh $INSTANCE --zone=$ZONE --tunnel-through-iap --command='cat ~/app/logs/bot-\$(date +%Y-%m-%d).log'"

# Cleanup
rm -f "$IMAGE_TAR"
