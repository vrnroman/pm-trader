# Deploy from your phone — one-time setup

The `Deploy` GitHub Action (`.github/workflows/deploy.yml`) lets you ship the
bot by tapping **Run workflow** in the GitHub mobile app. It runs the test
suite, then runs `poly_poly_bot/deploy.sh` from a GitHub-hosted runner that
authenticates to GCP and reaches the VM over an **IAP tunnel** (no public SSH).

Secrets live in **GitHub encrypted secrets** — never in a chat sandbox or the
repo. You do the steps below once.

---

## 1. GCP: create a least-privilege deploy service account

Run these in **GCP Cloud Shell** (shell.cloud.google.com — works on mobile).
Replace `PROJECT_ID` if yours differs from `roman-vm`.

```bash
PROJECT_ID=roman-vm
gcloud config set project "$PROJECT_ID"

# 1a. service account
gcloud iam service-accounts create poly-deployer \
    --display-name="Poly bot CI deployer"
SA="poly-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

# 1b. roles: manage the instance + its SSH-key metadata, tunnel via IAP,
#     and act as the VM's service account (needed for ssh/create)
for ROLE in roles/compute.instanceAdmin.v1 roles/iap.tunnelResourceAccessor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:${SA}" --role="$ROLE" --condition=None
done

# 1c. firewall: allow IAP's range to reach SSH (this is the *only* SSH ingress
#     you need — it is not open to the internet, only Google's IAP relays)
gcloud compute firewall-rules create allow-iap-ssh \
    --direction=INGRESS --action=ALLOW --rules=tcp:22 \
    --source-ranges=35.235.240.0/20 || echo "rule may already exist"

# 1d. download a key for the SA (paste its contents into GitHub in step 2)
gcloud iam service-accounts keys create /tmp/poly-deployer.json --iam-account="$SA"
cat /tmp/poly-deployer.json   # copy this whole JSON blob
```

> Security note: this SA can manage **only** Compute (the VM) and IAP tunneling
> — it has no access to your data, billing, or other services. Rotate the key
> any time with `gcloud iam service-accounts keys create/delete`.

## 2. GitHub: add the secrets and variable

In the GitHub mobile app or web: **repo → Settings → Secrets and variables →
Actions**.

**Secrets** (tab "Secrets"):

| Name | Value |
|------|-------|
| `GCP_SA_KEY` | the entire JSON from step 1d |
| `ENV_FILE` | the full contents of your `poly_poly_bot/.env` |

**Variable** (tab "Variables"):

| Name | Value |
|------|-------|
| `DEPLOY_SSH_USER` | the Linux username whose `~/app` holds the current deployment |

> Finding `DEPLOY_SSH_USER`: it's the user your local `bash deploy.sh` logs in
> as. To check, run once in Cloud Shell:
> `gcloud compute ssh poly-poly-bot --zone=asia-northeast1-a --tunnel-through-iap --command='ls -d /home/*/app'`
> and use the username in that path. **This must be correct** — a wrong user
> deploys into a different home directory and the bot won't see its existing
> `data/` volume (ledger, runtime state).

## 3. Deploy

- **From your phone:** GitHub app → repo → **Actions** tab → **Deploy** →
  **Run workflow** → pick the branch → Run. Watch the live logs in the app.
- **From a Claude chat:** ask Claude to trigger the `Deploy` workflow — it can
  start it and report the result via the GitHub integration.

Leave **Run the full test suite** checked unless you're re-deploying an already
green commit and want speed.

---

## Safety properties

- **Manual trigger only** — nothing deploys on push; a deploy is always a tap.
- **Test gate** — the workflow runs ruff F821 + the full pytest suite first and
  blocks deploy on failure.
- **Preview forced** — `deploy.sh` deletes `data/runtime_state.json` on every
  deploy, so the bot boots in `PREVIEW_MODE`. Live trading only re-arms via your
  explicit Telegram `/live 3 CONFIRM`.
- **Secrets isolated** — `.env` and the SA key exist only inside the ephemeral
  CI runner; the workflow deletes `.env` at the end and the runner is destroyed.
- **No open SSH** — the VM is reached only through IAP; the firewall rule admits
  Google's IAP relay range, not the internet.
- **Concurrency-guarded** — two deploys can't race onto the VM at once.

## Enabling the copy-paper loop (optional)

The paper-copy harness is default-off. To start it:

1. Generate a watchlist on the VM (Cloud Shell, IAP):
   `gcloud compute ssh poly-poly-bot --zone=asia-northeast1-a --tunnel-through-iap \
     --command='cd ~/app && docker run --rm -v ~/app/data:/app/data poly-poly-bot \
     python -m backtest.two_stage_watchlist --cache-dir data/wcache --output data/copy_watchlist.json'`
2. Add `COPY_PAPER_ENABLED=true` to your `ENV_FILE` secret.
3. Run the **Deploy** workflow.

It places no real orders — it only measures copy PnL net of drag, the gate for
graduating a wallet to real capital.
