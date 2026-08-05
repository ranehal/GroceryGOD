import re

with open('scratch.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new run_scraper and Market Scrapers section
new_code = '''            def run_scraper(scraper_info):
                label, path = scraper_info
                log.info(f'Starting {label}...')
                t0 = time.time()
                full_path = os.path.join(os.getcwd(), path)
                import glob
                script_targets = glob.glob(os.path.join(full_path, 'scraper*.py'))
                
                if not script_targets:
                    error_msg = f"No scraper scripts found in {full_path}"
                    log.error(f"X {error_msg}")
                    tg_send(f'X <b>{label}</b> - {error_msg}', silent=True)
                    return label, False, 0, "missing"

                my_env = os.environ.copy()
                total_lines = 0
                all_ok = True
                status_res = "ok"
                procs = []
                threads = []
                
                for script_target in script_targets:
                    try:
                        with open(script_target, 'r', encoding='utf-8') as f: code = f.read()
                        if 'DHAKA_TZ =' not in code:
                            patch = "import os\\nfrom datetime import timezone, timedelta\\nDHAKA_TZ = timezone(timedelta(hours=6))\\n"
                            with open(script_target, 'w', encoding='utf-8') as f: f.write(patch + code)
                    except: pass

                    script_name = os.path.basename(script_target)
                    proc = subprocess.Popen([sys.executable, script_name], cwd=full_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=my_env)
                    
                    stderr_capture = []
                    stdout_count = [0]
                    last_alive = [time.time()]
                    
                    def _read_stream(p, s_name, stream, is_stderr, capture, count, alive):
                        try:
                            for line in stream:
                                alive[0] = time.time()
                                if is_stderr:
                                    capture.append(line)
                                    log.warning(f'[{label}:{s_name} err] {line.rstrip()}')
                                else:
                                    count[0] += 1
                                    log.info(f'[{label}:{s_name}] {line.rstrip()}')
                        except: pass

                    t_stdout = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stdout, False, stderr_capture, stdout_count, last_alive), daemon=True)
                    t_stderr = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stderr, True, stderr_capture, stdout_count, last_alive), daemon=True)
                    t_stdout.start()
                    t_stderr.start()
                    
                    procs.append({
                        'proc': proc, 'name': script_name, 't_stdout': t_stdout, 't_stderr': t_stderr,
                        'stderr_capture': stderr_capture, 'stdout_count': stdout_count, 'last_alive': last_alive, 'timed_out': False, 'crashed': False
                    })
                
                # Monitor all procs
                deadline = time.time() + SCRAPER_TIMEOUT
                _last_10m_tg = None
                while True:
                    all_done = True
                    for p in procs:
                        if p['proc'].poll() is None:
                            all_done = False
                            _now = time.time()
                            # Intelligent stop: 10 mins without output
                            if _now - p['last_alive'][0] > 600:
                                p['proc'].kill()
                                p['timed_out'] = True
                                log.error(f"{label}:{p['name']} TIMED OUT (No output for 10m).")
                                tg_send(f"TIMEOUT <b>{label}:{p['name']}</b> (No output 10m).", silent=True)
                            
                            # Check cloudflare block in stderr
                            err_text = ''.join(p['stderr_capture'][-20:]).lower()
                            if 'cloudflare' in err_text or 'ip block' in err_text or '403 forbidden' in err_text:
                                p['proc'].kill()
                                p['crashed'] = True
                                log.error(f"{label}:{p['name']} BLOCKED (Cloudflare/IP).")
                                tg_send(f"BLOCKED <b>{label}:{p['name']}</b> (Cloudflare/IP issue).", silent=True)
                                
                    _now = time.time()
                    _elapsed = _now - t0
                    if _elapsed >= 1800:
                        if _last_10m_tg is None or (_now - _last_10m_tg) >= 600:
                            total_so_far = sum(p['stdout_count'][0] for p in procs)
                            proc_stats = "\\n".join([f" • {p['name']}: {p['stdout_count'][0]} lines ({'running' if p['proc'].poll() is None else 'finished'})" for p in procs])
                            status_msg = f"⏳ <b>{label}</b> Status Update — Running for {_fmt_dur(_elapsed)}\\nTotal lines: {total_so_far}\\n{proc_stats}"
                            log.info(f"[{label}] Sending 10-min TG status report ({_fmt_dur(_elapsed)} elapsed)...")
                            tg_send(status_msg, silent=True)
                            _last_10m_tg = _now

                    if all_done or time.time() > deadline:
                        break
                    time.sleep(5)
                
                for p in procs:
                    if p['proc'].poll() is None:
                        p['proc'].kill()
                        p['timed_out'] = True
                        tg_send(f"TIMEOUT <b>{label}:{p['name']}</b> (Hard deadline).", silent=True)
                    p['t_stdout'].join(timeout=5)
                    p['t_stderr'].join(timeout=5)
                    total_lines += p['stdout_count'][0]
                    if p['timed_out']:
                        all_ok = False; status_res = "timeout"
                    elif p['crashed'] or p['proc'].returncode != 0:
                        all_ok = False; status_res = "crashed"

                elapsed = time.time() - t0
                
                # Combine stats
                stats_msg = "\\n".join([f" - {p['name']}: {p['stdout_count'][0]} lines" for p in procs])
                if all_ok:
                    tg_msg = f"✅ 🟢 <b>{label}</b> — {_fmt_dur(elapsed)}\\n{stats_msg}"
                else:
                    tg_msg = f"⚠️ <b>{label}</b> finished with errors — {_fmt_dur(elapsed)}\\n{stats_msg}"

                tg_send(tg_msg, silent=False)
                return label, all_ok, total_lines, status_res

            with Step('History Reconstruction', '📄'):
                try:
                    subprocess.run([sys.executable, 'reconstruct_history.py'], check=True)
                    log.info("History successfully reconstructed from GitHub chunks.")
                except Exception as e:
                    log.error(f"History reconstruction failed: {e}. Proceeding with fresh start risk...")

            with Step('Market Scrapers (Serial)', '🛸'):
                import platform, os, subprocess
                if platform.system() == 'Windows':
                    shopno_dir = r'C:\PROJECTS\shopno'
                    othoba_dir = r'C:\PROJECTS\othoba'
                else:
                    shopno_dir = '/kaggle/working/shopno'
                    othoba_dir = '/kaggle/working/othoba'
                if not os.path.exists(shopno_dir):
                    subprocess.run(f'git clone https://github.com/ranehal/SHWAPNO-analylics.git "{shopno_dir}"', shell=True)
                if not os.path.exists(othoba_dir):
                    subprocess.run(f'git clone https://github.com/ranehal/Othoba-analytics.git "{othoba_dir}"', shell=True)
                
                scrapers = [
                    ('Shwapno', 'swapnoTRACKER'), 
                    ('Othoba', 'othobaTRACKER'), 
                    ('Chaldal', 'chaldalTRACKER'), 
                    ('Meena Bazar', 'MEENAtracker'), 
                    ('Unimart', 'unimartTRACKER'), 
                    ('Metro Mart', 'metroTRACKER'), 
                    ('ShotejBazar', 'ShotejTRACKER'), 
                    ('FooDIE', 'FooDIEscraper')
                ]
'''

# Find the start and end of the block to replace
start_idx = content.find('            def run_scraper(scraper_info):')
end_idx = content.find('                results = [None] * len(scrapers)', start_idx)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_code + content[end_idx:]
    with open('scratch.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Injected successfully.")
else:
    print("Could not find the target block.")

