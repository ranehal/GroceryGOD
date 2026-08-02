                                os.remove(p)
                        os.remove(base)
                    _enc_files = _glob.glob(os.path.join(_cwd, '**', '*.enc'), recursive=True)
                    log.info(f'  Found {len(_enc_files)} encrypted files')
                    _dc = 0
                    for ep in _enc_files:
                        try:
                            with open(ep, 'rb') as f: d = f.read()
                            plain = _dec(d, _KEY)
                            with open(ep[:-4], 'wb') as f: f.write(plain)
                            os.remove(ep)
                            _dc += 1
                            log.info(f'  {os.path.relpath(ep, _cwd)} -> decrypted ({len(plain)//1024}KB)')
                        except Exception as ex:
                            log.error(f'  ERROR {os.path.basename(ep)}: {ex}')
                    log.info(f'  Decrypted {_dc}/{len(_enc_files)} files')
                except subprocess.CalledProcessError as e:
                    log.error(f'Decryption failed: {e.stderr[:500]}')
                    tg_send(f'⚠️ <b>Repo Decryption</b> — failed (non-fatal)', silent=True)

            SCRAPER_TIMEOUT = 3 * 3600
            PARALLEL_MAX_WORKERS = 5
            ####################################################PARALLEL_MAX_WORKERS = 5
            def run_scraper(scraper_info):
                label, path = scraper_info
                log.info(f'Starting {label}...')
                t0 = time.time()
                full_path = os.path.join(os.getcwd(), path)
                script_target = os.path.join(full_path, 'scraper.py')

                if not os.path.exists(script_target):
                    error_msg = f"File scraper.py missing in {full_path}"
                    log.error(f"X {error_msg}")
                    tg_send(f'X <b>{label}</b> - {error_msg}', silent=True)
                    return label, False, 0, "missing"

                try:
                    with open(script_target, 'r', encoding='utf-8') as f:
                        code = f.read()
                    patch_marker = 'DHAKA_TZ = timezone(timedelta(hours=6))'
                    if patch_marker not in code:
                        log.info(f"Auto-Patching base imports into {label}...")
                        patch = "import os\nfrom datetime import timezone, timedelta\nDHAKA_TZ = timezone(timedelta(hours=6))\n"
                        with open(script_target, 'w', encoding='utf-8') as f:
                            f.write(patch + code)
                    else:
                        log.info(f"{label} already has base imports, skipping patch.")
                except Exception as patch_err:
                    log.warning(f"Failed to auto-patch {label}: {patch_err}")

                my_env = os.environ.copy()
                stderr_capture = []
                stderr_lock = threading.Lock()
                line_count = [0]
                last_tg_line = [0]
                proc = None

                def _read_stream(stream, is_stderr=False):
                    try:
                        for line in stream:
                            if is_stderr:
                                with stderr_lock: stderr_capture.append(line)
                                log.warning(f'[{label} stderr] {line.rstrip()}')
                            else:
                                line_count[0] += 1
                                log.info(f'[{label}] {line.rstrip()}')
                    except:
                        pass

                try:
                    proc = subprocess.Popen([sys.executable, 'scraper.py'], cwd=full_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=my_env)
                    t_stdout = threading.Thread(target=_read_stream, args=(proc.stdout, False), daemon=True)
                    t_stderr = threading.Thread(target=_read_stream, args=(proc.stderr, True), daemon=True)
                    t_stdout.start()
                    t_stderr.start()

                    _last_alive_tg = time.time()
                    _last_ss_tg = time.time()
                    _sent_screenshots = set()
                    _deadline = time.time() + SCRAPER_TIMEOUT
                    while time.time() < _deadline:
                        if proc.poll() is not None:
                            break
                        _now = time.time()
                        if _now - _last_ss_tg >= 300:
                            _elapsed_str = _fmt_dur(_now - t0)
                            import glob as _glob
                            _pngs = _glob.glob(os.path.join(full_path, '**', '*.png'), recursive=True)
                            for _png in _pngs:
                                if _png not in _sent_screenshots:
                                    try:
                                        tg_send_file(_png, f"📸 <b>{label}</b> 5-min Screenshot ({_elapsed_str})")
                                        _sent_screenshots.add(_png)
                                    except Exception: pass
                            tg_send(f"📸 <b>{label}</b> (Serial Run) — 5-min status update: {line_count[0]} lines ({_elapsed_str} elapsed)", silent=True)
                            _last_ss_tg = _now
                            _last_alive_tg = _now
                        elif _now - _last_alive_tg >= 300:
                            tg_send(f"<b>{label}</b> — status: {line_count[0]} lines ({_fmt_dur(_now-t0)} elapsed)", silent=True)
                            _last_alive_tg = _now
                        if line_count[0] - last_tg_line[0] >= 100:
                            last_tg_line[0] = line_count[0]
                            _last_alive_tg = _now
                        time.sleep(5)

                    timed_out = False
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=10)
                        elapsed = time.time() - t0
                        timed_out = True
                        log.error(f'{label} TIMED OUT after {_fmt_dur(elapsed)}!')
                        tg_send(f'TIMEOUT <b>{label}</b> after {_fmt_dur(elapsed)}! Partial data only.', silent=True)
                    else:
                        elapsed = time.time() - t0

                    t_stdout.join(timeout=30)
                    t_stderr.join(timeout=30)

                    if timed_out:
                        return label, False, line_count[0], "timeout"
                    if proc.returncode != 0:
                        stderr_text = ''.join(stderr_capture)
                        safe_err = stderr_text[:500]
                        log.error(f'{label} FAILED! RC={proc.returncode}')
                        tg_send(f'FAILED <b>{label}</b> in {_fmt_dur(elapsed)}!', silent=True)
                        return label, False, line_count[0], "crashed"
                except Exception as run_err:
                    elapsed = time.time() - t0
                    if proc and proc.poll() is None:
                        try: proc.kill()
                        except: pass
                    log.error(f'{label} EXCEPTION: {run_err}')
                    tg_send(f'EXCEPTION <b>{label}</b> after {_fmt_dur(elapsed)}!', silent=True)
                    return label, False, line_count[0], "exception"

                summary_log = ""
                log_file = os.path.join(full_path, "last_run_log.txt")
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r", encoding="utf-8") as f:
                            summary_log = f.read().strip()
                    except Exception as ex:
                        log.warning(f"Error reading {log_file} for {label}: {ex}")

                stderr_lines = len(stderr_capture)
                log.info(f'OK {label} finished in {_fmt_dur(elapsed)} (stdout={line_count[0]}, stderr={stderr_lines} lines)')
                
                if summary_log:
                    tg_msg = f"✅ 🟢 <b>{label}</b> — {_fmt_dur(elapsed)} ({line_count[0]} lines)\n{summary_log}"
                else:
                    tg_msg = f"✅ 🟢 <b>{label}</b> — {_fmt_dur(elapsed)} ({line_count[0]} lines)"

                tg_send(tg_msg, silent=False)
                return label, True, line_count[0], "ok"

            with Step('History Reconstruction', '📄'):
                try:
                    subprocess.run([sys.executable, 'reconstruct_history.py'], check=True)
                    log.info("History successfully reconstructed from GitHub chunks.")
                except Exception as e:
                    log.error(f"History reconstruction failed: {e}. Proceeding with fresh start risk...")

            with Step('Market Scrapers (Serial)', '\U0001f6f8'):
                import platform, os, subprocess
