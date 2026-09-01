from datetime import datetime, timezone, timedelta
import json
import os

DHAKA_TZ = timezone(timedelta(hours=6))
ts_dhaka = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA (UTC+6)")

with open("scratch.py", "r", encoding="utf-8") as f:
    source = f.read()

# scratch.py is the single source of truth for the notebook

# Load Kaggle notebook template
with open("kaggle gitGOD.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

# Rebuild cell 0 (header text block summary with timestamp and change log)
nb["cells"][0]["source"] = [
    "# 🚀 Parallel Execution: Continuous GroceryGOD (Simultaneous) + gitww\n",
    f"**Last Synchronized:** `{ts_dhaka}`\n",
    "\n",
    "Executes all scrapers completely simultaneously via multi-threading in an infinite loop alongside gitww. Features live notebook source persistence, AES-256 repo encryption, Parquet datasets, and 24/7 automated self-restarts.\n",
    "\n",
    "### 📋 Maintenance & Patch Log:\n",
    "- **🛡️ Self-Reboot IndentationError Fix & AST Validation Guard (2026-09-02)**: Fixed `IndentationError` caused by unindented in-place regex replacement of `_PERSISTED_SECRETS` and `_PERSISTED_STATE`. Strict column-0 matching (`^_PERSISTED_...`) prevents shadowing or breaking nested blocks, and pre-push `ast.parse()` guard guarantees that generated notebook code is 100% syntactically valid before container restart.\n",
    "- **⚡ Sub-Repo Sequential Execution & Directory Isolation (2026-09-02)**: Switched scheduled sub-repos to sequential execution with explicit `cwd` paths across all `subprocess.run` git and scraper calls. Completely eliminates multi-threading `os.chdir()` race conditions where threads clobbered repositories and caused 'No execution log or result found'.\n",
    "- **🔧 Python 3.12 TextIOWrapper Auto-Patcher & API Fallbacks (2026-09-02)**: Automatically replaces destructive `io.TextIOWrapper(sys.stdout.buffer)` with `sys.stdout.reconfigure()` across all cloned repos (fixing `ValueError: I/O operation on closed file` in Pickaboo). Auto-patches Chaldal `fetch_init` with cached metadata fallback (bypassing `FetchInitDataForCombinedStore` HTTP 500) and Cookups `fetch_categories` with 30s timeout and SQLite cache fallback.\n",
    "- **🔄 Kaggle Self-Reboot Multi-Tier Overhaul & State Telemetry (2026-09-01)**: Comprehensive multi-tier credential auto-loading (`UserSecretsClient`, `os.environ`, `_PERSISTED_SECRETS`, `~/.kaggle/kaggle.json`, disk vaults), automatic `kernel-metadata.json` sanitization, dynamic 2-cell payload recovery fallback, cross-restart state persistence (`_PERSISTED_STATE` tracking reboot counts and cycle metrics), and rich Telegram reboot telemetry dispatch featuring exact DHAKA timestamp, reboot count `#N`, session duration, pipeline completion badges (p1/p2/p3), and Parquet backup status.\n",
    "- **📊 Dedicated Scheduled Sub-Repos (p3–p14) Telegram Table Summary (2026-09-01)**: Direct Telegram dispatch upon sub-repos completion featuring a 1-look `<pre>` monospace table for all 12 scheduled sub-repos with Total products, ▲ Up, ▼ Down, New, OOS, and scrape duration, alongside in-stock/OOS percentages, stock movement deltas, and live dashboard URLs.\n",
    "- **🛡️ Pre-Flight GITHUB_PAT Verification & Telegram Fix Alert (2026-08-31)**: Comprehensive pre-execution validation of GITHUB_PAT against GitHub API (`/user` and repository write permissions). If PAT is missing, expired, revoked, or lacks push access, immediately dispatches a detailed Telegram alert containing diagnostic error and step-by-step resolution instructions for Kaggle.\n",
    "- **🔑 Seamless Self-Reboot Secret Persistence (2026-08-31)**: Fixed GITHUB_PAT and Kaggle secrets loss during automated kernel restarts. Replaced broken string-character iteration with dual in-place regex replacement and top-of-cell header injection in `trigger_self_restart()`, safeguarded `_PERSISTED_SECRETS` against in-code resets, added base64 decoding redundancy, and added disk-backed vault fallback.\n",
    "- **💾 Automated Parquet Dataset Backup for Manual Extraction (2026-08-31)**: Pre-encryption snapshots of all Parquet datasets, store chunks, and previews saved to clean date-separated versioned folders (`/kaggle/working/output/parquet_backup/YYYY-MM-DD/v{N}/`) with standalone 1-click ZIP archive and DuckDB extraction guide, preserving data even if Git push fails.\n",
    "- **📊 1-Look Monospace Table Telegram Summary (2026-08-25)**: Aggregator summary updated to format a single-look monospace `<pre>` table with Store, Total, ▲ Up, ▼ Down, New, and OOS counts plus grand total, compact source breakdown, and observed date ranges.\n",
    "- **⚡ Sub-Repo Bounded Concurrency & OOM Fix (2026-08-25)**: Replaced 12 simultaneous unconstrained processes with a managed 2-worker executor (`ThreadPoolExecutor(max_workers=2)`) to eliminate resource exhaustion and OOM kills on Kaggle.\n",
    "- **🏪 Chaldal App API Scraper Fix (2026-08-21)**: Switched to bulk catalog pagination over `searchPersonalized` (3,483 products collected in ~15s) with cached fallback for `FetchInitDataForCombinedStore` HTTP 500 error.\n",
    "- **📦 Stock Status & `-1.0` Sentinel (2026-08-21)**: Standardized out-of-stock items to `-1.0` in `history` and `history.parquet` (`first_seen`, `last_seen`, `in_stock`, `is_out_of_stock` in `products.parquet`). DuckDB queries filter `price > 0` for price analytics.\n",
    "- **🔓 Chunked `.enc.000` Decryption Fix (2026-08-21)**: Fixed premature `os.remove(base)` bug during chunk reassembly so multi-part encrypted archives (Othoba DB, Shwapno JSON) reassemble and decrypt properly.\n",
    "- **Scheduled Repo Auto-Resolution**: Fixed Meena Bazar Analytics (`MEEnaBAzar-analylics`) missing script error by auto-detecting target python scripts recursively (`backend/scraper.py`).\n",
    "- **Auto-Dependency Installation**: Fixed `ModuleNotFoundError: No module named 'playwright'` in scheduled sub-repos by auto-checking and installing `playwright`, `httpx`, and core scraper dependencies prior to execution.\n",
    "- **Full Multi-Threaded Store Orchestrators**: Parallel multi-threaded Web Playwright + App API execution for all store scrapers.\n"
]

# Rebuild cell 1 (python code source)
lines = source.splitlines(keepends=True)
nb["cells"][1]["source"] = lines

with open("kaggle gitGOD.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"Notebook rebuilt successfully at {ts_dhaka}.")
