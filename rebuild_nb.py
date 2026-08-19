import json
import os

with open("scratch.py", "r", encoding="utf-8") as f:
    source = f.read()

# scratch.py is the single source of truth for the notebook

# Load Kaggle notebook template
with open("kaggle gitGOD.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

# Rebuild cell 0 (header text block summary)
nb["cells"][0]["source"] = [
    "# 🚀 Parallel Execution: Continuous GroceryGOD (Simultaneous) + gitww\n",
    "Executes all scrapers completely simultaneously via multi-threading in an infinite loop alongside gitww. Features live notebook source persistence and Git LFS budget bypass protection across automated restarts.\n",
    "\n",
    "### 📋 Maintenance & Patch Log:\n",
    "- **10-Min TG Status Reports**: Sends status reports via Telegram every 10 mins for scrapers running longer than 30 mins.\n",
    "- **Scheduled Repo Auto-Resolution**: Fixed Meena Bazar Analytics (`MEEnaBAzar-analylics`) missing script error by auto-detecting target python scripts recursively (`backend/scraper.py`).\n",
    "- **Auto-Dependency Installation**: Fixed `ModuleNotFoundError: No module named 'playwright'` in scheduled sub-repos by auto-checking and installing `playwright`, `httpx`, and core scraper dependencies prior to execution.\n",
    "- **Parallel Execution & Unbuffered Output**: Fixed pipeline hangs by running scrapers in parallel with 5 thread workers, forcing unbuffered stdout (`-u` & `PYTHONUNBUFFERED=1`), and setting a 30-minute max timeout per scraper.\n",
    "- **Full Multi-Threaded Store Orchestrators**: Converted Meena Bazar, Chaldal, Othoba, and Shwapno store orchestrators from serial web/app routines to 100% parallel multi-threaded Web Playwright + App API execution.\n",
    "- **Sub-Repo CWD & PYTHONPATH Resolution**: Fixed missing file / import errors in sub-repos (e.g. `MEEnaBAzar-analylics/backend/scraper.py`) by setting `cwd` to the target script's parent folder and injecting script folder + repo root into `PYTHONPATH`.\n"
]

# Rebuild cell 1 (python code source)
lines = source.splitlines(keepends=True)
nb["cells"][1]["source"] = lines

with open("kaggle gitGOD.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print("Notebook rebuilt.")
