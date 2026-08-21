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
    "- **📊 Telegram Market Uplink & % Indicators (2026-08-21)**: Formats rich HTML summary (`📊 Aggregator Complete`) containing per-store and grand market totals for In-Stock vs Out-of-Stock (`%`), New Items (`%`), Price changes (🔺 Up, 🔻 Down, ⏸️ Same `%`), Stock deltas (🟢 Restocked vs 🔴 Went OOS `%`), and observed date ranges.\n",
    "- **🔕 Clean Telegram Protocol (No Spam)**: Only two Telegram events are permitted: `📊 Aggregator Complete` and `✅ Kaggle Restart Triggered Successfully!`. All intermediate and per-repo messages silenced.\n",
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
