import json

with open('kaggle gitGOD.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb.get('cells', []):
    if cell['cell_type'] == 'code':
        source = "".join(cell['source'])
        
        old_block = """                def _run_wrapper(idx, info):
                    return idx, run_scraper(info)

                log.info('Running scrapers serially one by one...')
                for idx, s in enumerate(scrapers):
                    log.info(f'Starting scraper {idx+1}/{len(scrapers)}: {s[0]}')
                    res = run_scraper(s)
                    results[idx] = res"""

        new_block = """                def _run_wrapper(idx, info):
                    return idx, run_scraper(info)

                log.info(f'Running scrapers in PARALLEL with {PARALLEL_MAX_WORKERS} workers...')
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_MAX_WORKERS) as executor:
                    futures = {executor.submit(_run_wrapper, idx, s): idx for idx, s in enumerate(scrapers)}
                    for future in concurrent.futures.as_completed(futures):
                        idx = futures[future]
                        try:
                            results[idx] = future.result()[1]
                        except Exception as e:
                            log.error(f'Parallel execution error for scraper {scrapers[idx][0]}: {e}')
                            results[idx] = (scrapers[idx][0], False, 0, "exception")"""

        if old_block in source:
            source = source.replace(old_block, new_block)
            lines = source.split('\n')
            cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]] if lines[-1] else []

with open('kaggle gitGOD.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)
