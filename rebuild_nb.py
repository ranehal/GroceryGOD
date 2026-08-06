import json
import os

with open("scratch.py", "r", encoding="utf-8") as f:
    source = f.read()

# 1. Apply GIT_TERMINAL_PROMPT patch
if "os.environ['GOD_PREMIUM_KEY'] = get_secret_safe('GOD_PREMIUM_KEY', 'assalamualaikum')\n" in source:
    source = source.replace(
        "os.environ['GOD_PREMIUM_KEY'] = get_secret_safe('GOD_PREMIUM_KEY', 'assalamualaikum')\n",
        "os.environ['GOD_PREMIUM_KEY'] = get_secret_safe('GOD_PREMIUM_KEY', 'assalamualaikum')\nos.environ['GIT_TERMINAL_PROMPT'] = '0'\n"
    )

# 2. Apply tail logs patch for run_scheduled_repo
old_exec_block = """        max_script_retries = 3
        for _attempt in range(1, max_script_retries + 1):
            print(f"[{label}] Executing {script_name} (attempt {_attempt}/{max_script_retries})...")
            t0 = time.time()
            my_env = os.environ.copy()
            res = subprocess.run([sys.executable, script_name], capture_output=True, text=True, timeout=5*18000, env=my_env)
            elapsed = time.time() - t0
            if res.returncode == 0:
                break
            safe_err = html.escape(res.stderr[:500])
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {script_name} failed:\\n{safe_err}")
            print(f"[WARN] {label} attempt {_attempt} failed (rc={res.returncode}), retrying...\\n{safe_err[:200]}")
            time.sleep(10)

        print(f"[{label}] Finished in {int(elapsed)}s. Pushing to GitHub...")"""

new_exec_block = """        max_script_retries = 3
        for _attempt in range(1, max_script_retries + 1):
            print(f"[{label}] Executing {script_name} (attempt {_attempt}/{max_script_retries})...")
            t0 = time.time()
            my_env = os.environ.copy()
            my_env["GIT_TERMINAL_PROMPT"] = "0"
            
            import threading
            import collections
            proc = subprocess.Popen([sys.executable, script_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=my_env)
            line_count = [0]
            stderr_capture = []
            stdout_last_lines = collections.deque(maxlen=15)
            
            def _read_stdout():
                for line in proc.stdout:
                    line_count[0] += 1
                    stdout_last_lines.append(line.strip())
            def _read_stderr():
                for line in proc.stderr:
                    stderr_capture.append(line)
                    
            t_out = threading.Thread(target=_read_stdout, daemon=True)
            t_err = threading.Thread(target=_read_stderr, daemon=True)
            t_out.start()
            t_err.start()
            
            _last_tg = time.time()
            while proc.poll() is None:
                if time.time() - _last_tg >= 300:
                    last_log = stdout_last_lines[-1] if stdout_last_lines else "Waiting for logs..."
                    tg_send(f"⏳ <b>{label}</b> (Attempt {_attempt}) — 5-min status: {line_count[0]} lines.\\nLog: {html.escape(last_log)[:100]}", silent=True)
                    _last_tg = time.time()
                time.sleep(5)
                
            t_out.join(timeout=30)
            t_err.join(timeout=30)
            elapsed = time.time() - t0
            
            if proc.returncode == 0:
                summary_log = ""
                log_file = "last_run_log.txt"
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r", encoding="utf-8") as f:
                            summary_log = f.read().strip()
                    except: pass
                
                if summary_log:
                    tg_send(f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count[0]} lines)\\n{summary_log}")
                else:
                    tail_logs = html.escape("\\n".join(list(stdout_last_lines)[-10:]))
                    tg_send(f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count[0]} lines)\\nTail logs:\\n<pre>{tail_logs}</pre>")
                break
                
            safe_err = html.escape("".join(stderr_capture)[:500])
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {script_name} failed:\\n{safe_err}")
            print(f"[WARN] {label} attempt {_attempt} failed (rc={proc.returncode}), retrying...\\n{safe_err[:200]}")
            time.sleep(10)

        print(f"[{label}] Finished in {int(elapsed)}s. Pushing to GitHub...")"""

if old_exec_block in source:
    source = source.replace(old_exec_block, new_exec_block)
else:
    print("Warning: old_exec_block not found in scratch.py!")

# 3. Modify success message
old_success = """tg_send(f"✅ <b>{label}</b> — Completed in {int(elapsed)}s! Pushed to GitHub.")"""
new_success = """tg_send(f"✅ <b>{label}</b> — Data Pushed to GitHub successfully.")"""
if old_success in source:
    source = source.replace(old_success, new_success)

# 4. Apply parallel processing patch
old_parallel_block = """                def _run_wrapper(idx, info):
                    return idx, run_scraper(info)

                log.info('Running scrapers serially one by one...')
                for idx, s in enumerate(scrapers):
                    log.info(f'Starting scraper {idx+1}/{len(scrapers)}: {s[0]}')
                    res = run_scraper(s)
                    results[idx] = res"""

new_parallel_block = """                def _run_wrapper(idx, info):
                    return idx, run_scraper(info)

                log.info(f'Running scrapers in PARALLEL with {PARALLEL_MAX_WORKERS} workers...')
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_MAX_WORKERS) as executor:
                    futures = {executor.submit(_run_wrapper, idx, s): idx for idx, s in enumerate(scrapers)}
                    for future in concurrent.futures.as_completed(futures):
                                             try:
                            results[idx] = future.result()[1]
                        except Exception as e:
                            log.error(f'Parallel execution error for scraper {scrapers[idx][0]}: {e}')
                            results[idx] = (scrapers[idx][0], False, 0, "exception")"""

if old_parallel_block in source:
    source = source.replace(old_parallel_block, new_parallel_block)
else:
    print("Warning: old_parallel_block not found in scratch.py!")

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
    "- **Auto-Dependency Installation**: Fixed `ModuleNotFoundError: No module named 'playwright'` in scheduled sub-repos by auto-checking and installing `playwright`, `httpx`, and core scraper dependencies prior to execution.\n"
]

# Rebuild cell 1 (python code source)
lines = source.splitlines(keepends=True)
nb["cells"][1]["source"] = lines

with open("kaggle gitGOD.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print("Notebook rebuilt.")
