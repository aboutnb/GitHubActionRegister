#!/usr/bin/env bash

set -euo pipefail

cd /app/backend

export WEB_ADMIN_SERVE_FRONTEND="${WEB_ADMIN_SERVE_FRONTEND:-true}"
export WEB_ADMIN_APP_ENV="${WEB_ADMIN_APP_ENV:-production}"
export WEB_ADMIN_DOCS_ENABLED="${WEB_ADMIN_DOCS_ENABLED:-false}"
export WEB_ADMIN_COOKIE_SECURE="${WEB_ADMIN_COOKIE_SECURE:-false}"
export WEB_ADMIN_FRONTEND_DIST="${WEB_ADMIN_FRONTEND_DIST:-../frontend/dist}"

python create_database.py
python init_db.py
python create_admin.py

exec python -m uvicorn app.main:app \
  --host "${WEB_ADMIN_HOST:-0.0.0.0}" \
  --port "${WEB_ADMIN_PORT:-18700}" \
  --workers "${WEB_ADMIN_WORKERS:-1}" \
  --log-level "${WEB_ADMIN_LOG_LEVEL:-info}"
