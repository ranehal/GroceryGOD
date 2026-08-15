# GroceryGOD — Agent Guide

Price-tracking engine for Bangladeshi grocery stores (Shwapno, Chaldal, Meena Bazar, Othoba, Metro Mart, Unimart, ShotejBazar, plus FoodPANDA/FooDIE/DARAZ/COOKup/PICAboo/CARTup sub-repos). Scrapers run continuously on **Kaggle** via a notebook, push data back to GitHub, and a static dashboard is served from GitHub Pages.

There is **no test suite, no linter, no CI, no requirements.txt**. Verification is: `ast.parse` the source, run `rebuild_nb.py`, confirm the notebook cell parses.

## Edit → deploy flow (the #1 trap)

- **`scratch.py` is the single source of truth** for the Kaggle orchestrator. Edit it, never the notebook directly.
- `rebuild_nb.py` regenerates `kaggle gitGOD.ipynb` from `scratch.py` (it also re-writes the markdown header cell and reapplies some patches). Run it after every scratch.py change.
- The notebook `kaggle gitGOD.ipynb` is **gitignored (`*.ipynb`) and untracked**; it is uploaded to Kaggle kernel `ranehalx/gitgod` (see `kernel-metadata.json`). Do not commit it.
- `test_run.py` is a **stale duplicate** of `scratch.py` (pre-dates the current fixes, not auto-generated). Never treat it as authoritative; do not edit it for the Kaggle pipeline.
- Repo history mixes auto-generated commits from the pipeline (`parallel scrapers {ts} (N/8 OK)`, `if this works ill get some sleep frfr {ts}`, `chore: daily price snapshot`) with manual `feat`/`fix` commits. Match existing style when committing; the pipeline commits are not "bad" commits to clean up.

## Kaggle orchestrator pipeline (in the notebook)

- One process per sub-repo (`run_scheduled_repo`) + `run_grocery_god` (main loop) + `run_gitw`, spawned via `multiprocessing`. Start order: p2 first, `time.sleep(600)`, then everything else. Total runtime cap 11h30m, then `pkill -9` teardown + Kaggle API self-restart.
- `run_grocery_god` loops forever (cycle → 8h sleep → cycle): clone/reset GroceryGOD repo (branch **`master`**) → decrypt `.enc` → run 8 in-repo store scrapers in parallel (ThreadPoolExecutor, 8 workers, 30-min hard timeout, 10-min-no-output kill) → `aggregator.py` → `convert_to_parquet.py` → repo encryption → `guardrail.py` → git push with force.
- Scheduled sub-repos: auto-install deps, auto-detect target script recursively, run with 3 retries, push with auth-URL fallback to whichever GitHub user owns the PAT.

## Hard-won concurrency rules (do not regress)

These fixes were extracted from live Kaggle failures. Preserve the patterns:

1. **Never bare-`import os` / `import subprocess` inside `run_grocery_god`** — a local `import os` in the function body shadows the module-level `os` for the whole function and crashes the first `os.chdir()` with `UnboundLocalError`. Any new module import needed inside a process function must be aliased (`import platform as _platform`) or added at module top.
2. **Git config writes race across processes** → `could not lock config file /root/.gitconfig` / `.git/config`. Always wrap `git config` via `_git_config()` (retries on "could not lock") inside `_with_lock('git-config', ...)`.
3. **`playwright install chromium --with-deps` runs `apt-get` and races** → `E: Could not get lock /var/lib/apt/lists/lock`. All chromium/apt installs must run inside `_with_lock('playwright-install', ...)` (fcntl-based, `/tmp/<key>.lck`).
4. **Disk fills during big clones** (`fatal: write error: No space left on device` kills the whole cycle). Call `_reclaim_disk()` before clones (purges pip cache, apt lists, `__pycache__`, `.pyc`, `_scraper_error_*.log`). The GroceryGOD clone is intentionally **shallow**: `git clone --depth 1 --single-branch --branch master --no-tags`.
5. **Chromium "missing" check** must verify the install dir exists on disk (parse `Install location:` from `playwright install --dry-run`), not match on the word "install" (that produced false positives).
6. Delete `_scraper_error_*.log` before `git add .` in sub-repo pushes so retry artifacts don't get committed.
7. **The GroceryGOD repo is `ranehal/GroceryGOD` — always clone and push as `ranehal`** via the embedded auth URL `https://ranehal:{pat}@github.com/ranehal/GroceryGOD.git` (`auth_grocery_url`); never via a bare URL (the credential store returning `ranehal` on a bare URL is fine, but a bare URL that yields the wrong user caused `403 denied`; embedded auth is the reliable pattern). Push iterates `auth_push_urls` (ranehal → bare).

## Pipeline change log (2026-08-14 — do not regress or redo)

- `import platform` moved to module top; deleted the local `import platform, os, subprocess` inside `run_grocery_god` (fix: `UnboundLocalError: os` killing the whole pipeline at boot).
- Added helpers: `_with_lock(lock_key, fn)` (fcntl, `/tmp/<key>.lck`, Windows no-op fallback), `_git_config(cmd)` (retry on "could not lock"), `_reclaim_disk(force=False)` (purges pip cache / apt lists / `__pycache__` / `.pyc` / `_scraper_error_*.log`, returns free GB).
- Git config setup and playwright/apt installs in both `run_grocery_god` and `run_scheduled_repo` are serialized under `_with_lock('git-config', ...)` / `_with_lock('playwright-install', ...)` (fix: `.gitconfig` / `.git/config` and `/var/lib/apt/lists/lock` races).
- GroceryGOD clone is shallow (`--depth 1 --single-branch --branch master --no-tags`) + `_reclaim_disk(force=True)` before it; sub-repos call `_reclaim_disk()` before cloning (fix: `No space left on device`).
- Chromium verification parses `Install location:` from `playwright install --dry-run` and checks the dir exists (fix: false-positive "Chromium may still be missing").
- `run_scheduled_repo`: "Run Started" Telegram message removed; successful push sends only `🔗 https://ranehal.github.io/{repo_name}/` (no more Telegram spam; success = just the live page URL).
- **p14 Telegram reporting — ONE consolidated message, no spam (2026-08-16, do not regress)**: after **all** scheduled repos (p3–p14) finish, `_send_p14_summary` sends a single Telegram message containing: per-repo label, scrape time (m/s), product counts, live URL, and a `<pre>` detail/error log for any failed repo + the aggregator summary (polled from `/tmp/aggregator_summary.txt`). No per-repo TG messages. `aggregator.py` writes the shared summary file **only** — it must NOT send its own Telegram message. The GroceryGOD cycle `report.txt` (`/tmp/grocerygod_cycle_report.txt`) is written locally but **never sent via `tg_send_file`**.
- **Per-store scrape source (aggregator summary, 2026-08-16)**: `STORE_SOURCES` in `aggregator.py` — `foodi` = **app-API only** (stats report `app_scraped`, never `web_scraped`); `metromart`/`unimart`/`shotejbazar` = **web-only** (web line only, no `App scraped: 0` noise). The summary shows only the lines for the store's actual source(s), plus a `📅 Price data: <min> to <max>` date range from the loader's `date_range`.
- GroceryGOD push authenticates via embedded auth URLs only (fix: bare-URL pushes fell back to the credential store and hit `403 denied to ranehal` on the repo; see rule 7).
- GroceryGOD repo switched to **`ranehal/GroceryGOD`**: clone, origin, and push all use `https://ranehal:{pat}@github.com/ranehal/GroceryGOD.git` (`auth_grocery_url`), git identity set to `ranehal`, and the Telegram success link now points to `https://ranehal.github.io/GroceryGOD` (see rule 7).
- **All `ranx-x` references removed** — the credential store, `auth_push_urls`/`auth_user_urls` (now ranehal → bare), git `user.name`, clone/origin URLs, and Telegram links contain no dependency on the `ranx-x` account.
- Environment Sync is now **non-fatal and resilient**: `pip install` and `playwright install chromium --with-deps` failures no longer kill `run_grocery_god` — chromium falls back to a plain `install chromium` (no apt), then degrades to a warning so the loop still boots (fix: `Environment Sync — FAILED` terminating GroceryGOD at startup).
- **Othoba "App scraped: 0" fixed** (aggregator.py + othobaTRACKER/scraper.py): the app-data path was missing the `/frontend/` segment (`othoba_products.json` actually lives at `frontend/othoba_products.json` — in the repo and in the `Othoba-analytics` sub-repo), so the aggregator always found 0. Web data now loads from the decrypted `othoba_tracker.db` (real website scrape incl. `price_history`) with the JSON as fallback; app data loads from `frontend/othoba_products.json` (mobile-API scraper). `othobaTRACKER/scraper.py`'s web/app split also fixed (app JSONs were being dumped into `web_products`, so its log always printed `App API Scraped: 0`). **Metromart/Unimart/Shotejbazar/Foodi `App scraped: 0` is by design** — they have no mobile-app scraper; aggregator hardcodes 0 (aggregator.py `load_metromart`/`load_unimart`/`load_shotejbazar`/`load_foodi`).

## Encryption & secrets

- Sensitive data is committed **encrypted** as `.enc` (AES-256-GCM, PBKDF2-SHA256 250k iters, magic `GGE1`; files >40MB split into `.enc.NNN` chunks). The notebook decrypts inline at runtime and re-encrypts before push.
- `encrypt_repo.py`, `decrypt_repo.py`, `update_premium_key.py`, `decrypt_premium.py` are **gitignored / local-only** tools. Never commit plaintext `.db`, raw `data.js`/`data.json`, or scraper source for the stores — they must be re-encrypted first.
- Secrets come from Kaggle secrets or env: `GITHUB_PAT`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, `KAGGLE_KERNEL_SLUG`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GOD_PREMIUM_KEY`. All are read via `get_secret_safe()`. Never log a PAT/token.

## Data pipeline & artifacts

- Per-store scrapers live in tracker dirs (`swapnoTRACKER`, `PRICETRACKER`, `MEENAtracker`, `othobaTRACKER`, `metroTRACKER`, `unimartTRACKER`, `ShotejTRACKER`, `FooDIEscraper`); each writes a `last_run_log.txt` and data files.
- `aggregator.py` normalizes prices to per-unit (BDT/kg, BDT/L, BDT/pc) and emits lazy-loaded JS chunks `*_data_part*.js` + `*_manifest.js` (static CDN can't serve >~50MB files).
- `convert_to_parquet.py` builds `products.parquet`/`history.parquet` plus free-tier `*_free.parquet`; the full archive is `premium/history_archive.parquet.enc`.
- `reconstruct_history.py`, `rescue_april_data.py`, `rescue_feb_data.py`, `fill_history_gaps.py` are one-off history-repair utilities — read before running; they mutate history data.
- `guardrail.py` aborts a push if any vital file is an LFS pointer or >98MB (GitHub 100MB limit). It's invoked by the notebook's GitHub Push Guard step.
- Main GroceryGOD repo uses branch `master`; sub-repos auto-detect their default branch.

## Frontend

- GitHub Pages dashboard: `index.html`, `style.css`, `script.js`, `categories.js` (+ generated chunks/manifests). Live at `https://ranehal.github.io/GroceryGOD`.
- Local dev: `python dev_server.py` serves the dashboard at `http://localhost:8888` (CORS + no-cache headers included).
