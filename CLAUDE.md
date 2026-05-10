# Project rules for Claude

## Testing

- **Always run the FULL test suite when changing code in this repo.** No subsets, no "just the relevant ones." Run every test in `poly_poly_bot/tests/` (currently 363 tests).
- The local venv at `poly_poly_bot/.venv` must have all of `requirements.txt` installed before running tests. If `pytest` fails on import errors (e.g. `py_clob_client`, `web3`, `pandas`), run `.venv/bin/pip install -r requirements.txt` first instead of skipping the broken modules.
- Command: `cd poly_poly_bot && .venv/bin/python -m pytest tests/ -q`
- Reporting: state the actual count (e.g. "363 passed"), not "all tests pass" without a number.

## Ship workflow (poly_poly_bot)

After any edit under `poly_poly_bot/`, run the full cycle without asking:
1. Full test suite must pass.
2. `git add` the touched files, commit, `git push`.
3. `cd poly_poly_bot && bash deploy.sh` to redeploy to GCP.
