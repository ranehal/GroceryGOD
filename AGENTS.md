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
- **p14 Telegram reporting — ONE consolidated message, no spam (2026-08-16, do not regress)**: after **all** scheduled repos (p3–p14) finish, `_send_p14_summary` sends a single Telegram message containing: per-repo label, scrape time (m/s), product counts, live URL, and a `<pre>` detail/error log for any failed repo + the aggregator summary (polled from `/tmp/aggregator_summary.txt`). No per-repo TG messages. `aggregator.py` writes the shared summary file **only** — it must NOT send its own Telegram message. The GroceryGOD cycle `report.txt` (`/tmp/grocerygod_cycle_report.txt`) is written locally but **never sent via `tg_send_file`**. **Results are exchanged via per-repo JSON files `/tmp/p14_result_<label>.json`** (written by `_store_result`, read by `_send_p14_summary`) — the `multiprocessing.Manager` dict silently failed on Kaggle (all 12 repos reported FAILED 0m 0s "unknown error" despite success); files are the source of truth, the manager dict is only a best-effort fallback. Stale result files are deleted at orchestrator start.
- **`reconstruct_history.py` must never die on one store** (2026-08-16, do not regress): a single crash (Meena `p['category']` being a dict from `catalog.json` — `{"id":..,"name":..,"slug":..}` — bound into sqlite) previously killed the WHOLE script → every store lost its full history merge ("Proceeding with fresh start risk" → aggregator date ranges shrank to days). Each store's reconstruction is now wrapped in try/except (one failure skips only that store), and `_cat_name()` normalizes category dicts to strings in all four DB rebuilders. The history archive itself is never lost — it lives in `history.parquet` (min `2026-02-15`); only the per-store working files lose depth when reconstruction is skipped.
- **Per-store scrape source (aggregator summary, 2026-08-16)**: `STORE_SOURCES` in `aggregator.py` — `foodi` = **app-API only** (stats report `app_scraped`, never `web_scraped`); `metromart`/`unimart`/`shotejbazar` = **web-only** (web line only, no `App scraped: 0` noise). The summary shows only the lines for the store's actual source(s), plus a `📅 Price data: <min> to <max>` date range from the loader's `date_range`.
- GroceryGOD push authenticates via embedded auth URLs only (fix: bare-URL pushes fell back to the credential store and hit `403 denied to ranehal` on the repo; see rule 7).
- GroceryGOD repo switched to **`ranehal/GroceryGOD`**: clone, origin, and push all use `https://ranehal:{pat}@github.com/ranehal/GroceryGOD.git` (`auth_grocery_url`), git identity set to `ranehal`, and the Telegram success link now points to `https://ranehal.github.io/GroceryGOD` (see rule 7).
- **All `ranx-x` references removed** — the credential store, `auth_push_urls`/`auth_user_urls` (now ranehal → bare), git `user.name`, clone/origin URLs, and Telegram links contain no dependency on the `ranx-x` account.
- Environment Sync is now **non-fatal and resilient**: `pip install` and `playwright install chromium --with-deps` failures no longer kill `run_grocery_god` — chromium falls back to a plain `install chromium` (no apt), then degrades to a warning so the loop still boots (fix: `Environment Sync — FAILED` terminating GroceryGOD at startup).
- **Othoba "App scraped: 0" fixed** (aggregator.py + othobaTRACKER/scraper.py): the app-data path was missing the `/frontend/` segment (`othoba_products.json` actually lives at `frontend/othoba_products.json` — in the repo and in the `Othoba-analytics` sub-repo), so the aggregator always found 0. Web data now loads from the decrypted `othoba_tracker.db` (real website scrape incl. `price_history`) with the JSON as fallback; app data loads from `frontend/othoba_products.json` (mobile-API scraper). `othobaTRACKER/scraper.py`'s web/app split also fixed (app JSONs were being dumped into `web_products`, so its log always printed `App API Scraped: 0`). **Metromart/Unimart/Shotejbazar/Foodi `App scraped: 0` is by design** — they have no mobile-app scraper; aggregator hardcodes 0 (aggregator.py `load_metromart`/`load_unimart`/`load_shotejbazar`/`load_foodi`).
- **Chaldal "App scraped: 0" fixed (2026-08-21, do not regress)**: `chaldalTRACKER/scraper_app.py` previously crashed on `FetchInitDataForCombinedStore` HTTP 500 before scraping products. `scrape_all_catalog()` now scrapes the full catalog in bulk via direct pagination over `https://catalog.chaldal.com/searchPersonalized` (`pageSize=100`, `canSeeOutOfStock="true"`), collecting all 3,483 app products in ~15s. `fetch_init` is wrapped with a cached `categories.json` fallback. Aggregator and orchestrator load both Web (`data.js`) and App API (`data/products.json` + `data/price_history.json`).
- **Telegram Message Whitelist (STRICT — only 2 message types allowed, do not regress)**:
  1. `📊 <b>Aggregator Complete</b>`: Formatted rich HTML summary generated by `aggregator.py` and sent by `run_grocery_god` after push, containing per-store & grand market metrics with counts, percentages (`%`), price up/down/same, stock deltas (restocked / went OOS), and live URL. Split into chunks if >3900 chars.
  2. `✅ <b>Kaggle Restart Triggered Successfully!</b>`: Self-reboot container trigger notification sent by `trigger_self_restart()`.
  - **All other Telegram messages are SILENCED**: No "Run Started" alerts, no individual sub-repo push messages, no 11h timeout warning messages, and no separate `report.txt` file sends. `_send_p14_summary` writes to `/tmp/p14_summary.log` locally only.
- **Notebook Header Box & Timestamp Auto-Sync (`rebuild_nb.py`, do not regress)**: Each time `kaggle gitGOD.ipynb` is updated, `rebuild_nb.py` regenerates Cell 0 with the exact synchronization timestamp (`YYYY-MM-DD HH:MM:SS DHAKA (UTC+6)`) and comprehensive patch log alongside the Python code in Cell 1.
- **Out-of-Stock `-1.0` Sentinel & Stock Tracking (2026-08-21, do not regress)**:
  - Scraper out-of-stock points and zero/negative prices are standardized to `-1.0` sentinel in `history` arrays and `history.parquet` (`price = -1.0`, `normalized_price = -1.0`).
  - `products.parquet` schema maintains `first_seen`, `last_seen`, `in_stock` (BOOLEAN), `is_out_of_stock` (BOOLEAN).
  - Frontend DuckDB queries filter `WHERE h.price > 0` for `min_price`, `max_price`, and `avg_price` calculations to prevent `-1.0` sentinels from corrupting historical statistics. Chart.js plots `-1.0` as `null` with `spanGaps: true` and shows `"Out of Stock (-1)"` in tooltips. Product detail modal displays First Seen, Last Seen, and Stock Status badges.
- **Chunked `.enc.000` reassembly bugfix (2026-08-21, do not regress)**: In `scratch.py` and `decrypt_repo.py`, removed premature `os.remove(base)` before decryption so multi-part chunked files (`othobaTRACKER/othoba_tracker.db.enc.000/.001`, `swapnoTRACKER/data.json.enc.000/.001`) reassemble and decrypt properly.
- **Othoba Grocery Scoping & Othoba-Analytics Separation (2026-08-22, do not regress)**:
  - GroceryGOD strictly scrapes and aggregates **grocery-only categories** from Othoba (`https://othoba.com/daily-bazar`, `https://othoba.com/daily-shopping`, `https://othoba.com/food-grocery`, `https://othoba.com/monthly-grocery-mega-discounts`, `https://othoba.com/bogo-grocery-month` and their subcategories).
  - All non-grocery products (electronics, clothing, watches, furniture, books, medicines, gadgets, etc. ~112k items) and their complete historical price records are omitted from GroceryGOD and maintained in the standalone `https://github.com/ranehal/Othoba-analytics.git` repository (`C:\PROJECTS\ShopGOD\othoba`).
  - `othobaTRACKER/urls.txt`, `othobaTRACKER/scraper_app.py`, and `aggregator.py` (`load_othoba()`) strictly enforce `is_othoba_grocery_category` to exclude non-grocery items. `othobaTRACKER/othoba_tracker.db` is reduced to ~3MB with ~4,800 clean grocery products (2 chunks, no chunk splitting needed).
- **Single-Cycle p1 & Orchestrator Restart Fix + p3-p14 Price Stats (2026-08-22, do not regress)**:
  - `run_grocery_god` runs a single complete cycle and exits without sleeping for 12 hours.
  - Master orchestrator has an 11-hour safety cap (`timeout_seconds = 11 * 3600`) well under Kaggle's 12-hour (43,200s) hard ceiling, triggering nuclear teardown and container restart via `trigger_self_restart()`.
  - Sub-repo scrapers (p3–p14) extract full price change metrics (up, down, unchanged/same counts and `%`, new items, in-stock/out-of-stock) across SQLite databases, JSON catalogs, and historical snapshots, logged in `/tmp/p14_summary.log`.
- **Aggregator Chunking Infinite Loop Fix (2026-08-23, do not regress)**:
  - Replaced the retry while-loop in `aggregator.py` (`save_store_data`) with a linear single-pass byte-budget chunk partitioner (`MAX_FILE_SIZE_MB = 45`, target `40.5MB` cap). Prevents infinite retry loop when a store's deep historical records exceed chunk thresholds.
- **Sub-repo Price Stats `glob` Import Fix & In-Repo Scraper Cleanup (2026-08-23, do not regress)**:
  - Added `import glob` at module top and inside `_extract_repo_price_stats` in `scratch.py` to prevent `NameError: name 'glob' is not defined`.
  - Removed `FooDIEscraper` from in-repo parallel scrapers list (since FooDIE Mart is a separate sub-repo `p5`) and added automatic DB sync from `/kaggle/working/FooDIE-mart-Analytics/data/scraper.db` before aggregator runs. Increased `SCRAPER_TIMEOUT` to 45 minutes (`45 * 60`).
- **1-Look Monospace Table Telegram Summary & Sub-Repo Concurrency Control (2026-08-25, do not regress)**:
  - `aggregator.py` formats the Telegram summary as a clean, single-screen `<pre>` monospace table with Store, Total, ▲ Up, ▼ Down, New, and OOS counts plus grand total, compact source breakdown, and observed date ranges.
  - Replaced 12 simultaneous unconstrained processes with a managed 2-worker executor (`ThreadPoolExecutor(max_workers=2)`) in `scratch.py` to eliminate resource exhaustion and OOM kills on Kaggle.
  - Strict Telegram whitelist enforced: Only `📊 Aggregator Complete` (1-look table) and `✅ Kaggle Restart Triggered Successfully!` sent to Telegram. Scheduled sub-repo summary logged to `/tmp/p14_summary.log` locally.
- **Awwwards Editorial Hero, Magnetized Catalog & Progressive Store Chunking (2026-08-28, do not regress)**:
  - Added full-screen Awwwards-inspired editorial landing hero section above `.app-container` with glowing aurora mesh, real-time live Dhaka intelligence badge, 80,153+ product telemetry, interactive mirrored search box with quicktags, direct store chips, and smooth scroll down CTA.
  - Magnetized catalog section: Full `100vw` sticky layout. Entering catalog anchors view to items; `#header-hero-tab` and brand mark smoothly return user up to the Hero overview.
  - Progressive Per-Store History Chunking: Removed blocking 33.5MB history preload in `index.html`. `script.js` boots with only `products_free.parquet` (2.2MB, ~800ms first paint). Background hydration streams `history_shwapno.parquet` first (~4.9MB), refreshes badges, then streams remaining 7 store chunks in parallel via `Promise.allSettled`.
  - DuckDB `history_access` view dynamically unions all loaded store chunks (`history_*.parquet`). Paywall and premium unlock (`unlockPremiumArchive()`) cleanly union decrypted `history_archive.parquet` into `history_access` with zero regressions or conflicts.
- **Automated Parquet Dataset Backup for Manual Extraction (2026-08-31, do not regress)**:
  - Kaggle notebook outputs are organized into clean, isolated date-separated and versioned folders at `/kaggle/working/output/parquet_backup/YYYY-MM-DD/v{N}/` outside cloned repo directories.
  - Automatically captures pre-encryption snapshots of all unencrypted datasets (`products.parquet`, `history.parquet`, `products_free.parquet`, `history_free.parquet`, `atl.parquet`, `atl_preview.json`, all `history_<store>.parquet` chunks, and `premium/` archive parquets).
  - Bundles an all-in-one standalone ZIP archive (`grocerygod_parquet_YYYY-MM-DD_v{N}.zip`), copies a convenience shortcut `latest_parquet_backup.zip` to the output root, writes `backup_summary.json` with file sizes and row counts, and provides `README_MANUAL_EXTRACTION.txt` with DuckDB querying instructions.
  - Safeguards data if Git push or authentication fails: sets `git_status='GIT_PUSH_FAILED'` in `backup_summary.json` and outputs a prominent extraction path banner to console and failure alerts.
- **Seamless Self-Reboot Secret Persistence (`trigger_self_restart`, 2026-08-31, do not regress)**:
  - Kaggle `kernels_push` converts code cell sources from list of lines to a single string; previous line-by-line iteration treated the string as a sequence of single characters, causing `l.startswith('_PERSISTED_SECRETS =')` to fail and inject duplicates while line 316 unconditionally wiped `_PERSISTED_SECRETS = {}` on container boot.
  - Replaced line loop with direct regex in-place replacement (`re.subn(r'^[ \t]*_PERSISTED_SECRETS\s*=.*$', ...)`) and top-of-cell bootstrap header block injection with dual JSON and base64 payloads.
  - Safeguarded `_PERSISTED_SECRETS` initialization in `scratch.py` (`if '_PERSISTED_SECRETS' not in globals() or not isinstance(_PERSISTED_SECRETS, dict) or not _PERSISTED_SECRETS: _PERSISTED_SECRETS = {}`).
  - Added base64 decoding check (`_PERSISTED_SECRETS_B64`) and local vault file fallbacks (`/kaggle/working/secrets_vault.json`, `/kaggle/working/output/secrets_vault.json`, `/tmp/secrets_vault.json`) in `get_secret_safe()`.
- **Pre-Flight GITHUB_PAT Verification & Telegram Fix Alert (`run_preflight_checks`, 2026-08-31, do not regress)**:
  - Added `verify_github_pat(pat)` and `send_preflight_telegram_alert(diagnosis, fix_instructions)` to validate `GITHUB_PAT` before scrapers spawn.
  - Queries GitHub API (`GET /user` and `GET /repos/ranehal/GroceryGOD`) to verify token authenticity, active status, and push/write permissions.
  - If the token is missing, expired, revoked (HTTP 401), or lacks repository write access, dispatches a detailed Telegram alert with step-by-step resolution instructions for Kaggle (generating token with `repo` scope, attaching via **Add-ons > Secrets**, checking the enable box, and restarting the kernel).



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
- **Chatbot (GroceryGOD Assistant)**: Tier-0 offline rule-based answers over the in-browser DuckDB parquet (intents: cheapest, compare store A vs B, price of X, history/trend, product counts, which store sells X, categories) + Tier-1 free-tier Gemini (`gemini-2.5-flash`) with function calling when the user adds a key. The Gemini key is user-entered at runtime and stored **only** in `localStorage` under `god_gemini_key` (via `safeStorage` in `script.js`); it must **never** be hardcoded, committed, or logged. Tools execute against local data and only aggregates leave the browser. Do not rename/remove the chat widget DOM (`#god-chat-*` in `index.html`) or the `CHAT_*` helpers in `script.js` without keeping the storage contract.
