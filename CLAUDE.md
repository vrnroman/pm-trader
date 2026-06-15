# Project rules for Claude

## Testing

- **Always run the FULL test suite when changing code in this repo.** No subsets, no "just the relevant ones." Run every test in `poly_poly_bot/tests/` (currently 363 tests).
- The local venv at `poly_poly_bot/.venv` must have all of `requirements.txt` installed before running tests. If `pytest` fails on import errors (e.g. `py_clob_client`, `web3`, `pandas`), run `.venv/bin/pip install -r requirements.txt` first instead of skipping the broken modules.
- Command: `cd poly_poly_bot && .venv/bin/python -m pytest tests/ -q`
- Reporting: state the actual count (e.g. "363 passed"), not "all tests pass" without a number.

## Ship workflow (poly_poly_bot)

After any edit under `poly_poly_bot/`, run the full cycle without asking:
1. Full test suite must pass.
2. `git add` the touched files, commit, `git push` to `main`.
3. Deploy is automatic on push to `main`: the GitHub Actions `Deploy` workflow
   runs the test gate, then **builds the Docker image on the runner** (native
   amd64) and ships the finished image to the GCP VM, which only `docker load`s
   + runs it. Watch it with `gh run watch <id>` and confirm the container comes
   up clean. Do NOT run `bash deploy.sh` on this Mac — it now builds the image
   locally and the Mac has no Docker (it's arm64; the VM is amd64). `deploy.sh`
   is for the CI runner or any docker-equipped amd64 host.

The VM (`poly-poly-bot`, zone `asia-northeast1-a`, project `roman-vm`) is an
`e2-small` reached only via IAP (`gcloud compute ssh ... --tunnel-through-iap`).
It has gone network-dead before (metadata server unreachable → SSH fails with
"failed to connect to port 22"); a `gcloud compute instances reset` recovers
it and the container auto-restarts (`--restart unless-stopped`).
