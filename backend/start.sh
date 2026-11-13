#!/bin/sh
# Container / PaaS entrypoint: create tables (idempotent), optionally load demo data, start the API.
set -e
python -m app.init_db
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then python -m app.seed; fi
# --proxy-headers: hosts put a trusted proxy in front, so the rate limiter sees the real client address.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
