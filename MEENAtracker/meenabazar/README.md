# Meena price-tracker scraper starter

This starter contains the HAR-derived **runtime scraper only**. It does not read the HAR and does not contain the captured bearer token or personal account data.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MEENA_BEARER_TOKEN='fresh-authorized-token'
python scripts/scrape.py
```

It writes `public/data/catalog.json`, `sections.json`, `meta.json`, and 256 on-demand price-history shards under `public/data/history/`.

## GitHub Actions

Add `MEENA_BEARER_TOKEN` under **Repository settings → Secrets and variables → Actions**. The included workflow runs daily at 06:30 Asia/Dhaka and commits only changed data.

## Security

The uploaded HAR contains a reusable bearer credential and personal account fields. Revoke/rotate that credential, do not commit the HAR, and do not expose a token in browser code. Use only an account and API access you are authorized to automate, with a conservative request rate and the service's applicable terms.
