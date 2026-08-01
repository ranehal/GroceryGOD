import json
import re

with open('kaggle gitGOD.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb.get('cells', []):
    if cell['cell_type'] == 'code':
        source = cell['source']
        full_source = "".join(source)
        
        # 2. Rewrite run_scheduled_repo execution block
        old_exec_block = """        max_script_retries = 3
        for _attempt in range(1, max_script_retries + 1):
            print(f"[{label}] Executing {script_name} (attempt {_attempt}/{max_script_retries})...")
            t0 = time.time()
            my_env = os.environ.copy()
            my_env["GIT_TERMINAL_PROMPT"] = "0"
            
            import threading
            proc = subprocess.Popen([sys.executable, script_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=my_env)
            line_count = [0]
            stderr_capture = []
            
            def _read_stdout():
                for line in proc.stdout:
                    line_count[0] += 1
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
                    tg_send(f"⏳ <b>{label}</b> (Attempt {_attempt}) — 5-min status update: {line_count[0]} items scraped so far.", silent=True)
                    _last_tg = time.time()
                time.sleep(5)
                
            t_out.join(timeout=30)
            t_err.join(timeout=30)
            elapsed = time.time() - t0
            
            if proc.returncode == 0:
                summary_log = ""
                log_file = "last_run_log.txt"
                import os
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r", encoding="utf-8") as f:
                            summary_log = f.read().strip()
                    except: pass
                
                if summary_log:
                    tg_send(f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count[0]} lines)\\n{summary_log}")
                else:
                    tg_send(f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count[0]} lines)")
                break
                
            safe_err = html.escape("".join(stderr_capture)[:500])
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {script_name} failed:\\n{safe_err}")
            print(f"[WARN] {label} attempt {_attempt} failed (rc={proc.returncode}), retrying...\\n{safe_err[:200]}")
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
                import os
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

        if old_exec_block in full_source:
            full_source = full_source.replace(old_exec_block, new_exec_block)
            
        # Write lines back
        lines = full_source.split('\n')
        cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]] if lines[-1] else [line + '\n' for line in lines[:-1]]

with open('kaggle gitGOD.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)
