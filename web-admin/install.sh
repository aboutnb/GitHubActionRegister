#!/usr/bin/env bash

set -euo pipefail

REPO="__REPO__"
TARGET_DIR="${WEB_ADMIN_TARGET_DIR:-/opt/web-admin}"
TMP_DIR="${TMPDIR:-/tmp}"
SERVICE_NAME="${WEB_ADMIN_SERVICE_NAME:-web-admin}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_USER="${WEB_ADMIN_SERVICE_USER:-$(id -un)}"

ARCHIVE_URL="https://github.com/${REPO}/releases/latest/download/web-admin.tar.gz"
ARCHIVE_PATH="${TMP_DIR}/web-admin.tar.gz"

curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
sudo mkdir -p "$(dirname "$TARGET_DIR")"
sudo mkdir -p "$TARGET_DIR"

if [[ -d "$TARGET_DIR/backend" ]]; then
  sudo find "$TARGET_DIR/backend" -mindepth 1 -maxdepth 1 \
    ! -name '.env' \
    ! -name '.venv' \
    -exec rm -rf {} +
fi
if [[ -d "$TARGET_DIR/frontend" ]]; then
  sudo rm -rf "$TARGET_DIR/frontend"
fi
if [[ -d "$TARGET_DIR" ]]; then
  sudo find "$TARGET_DIR" -mindepth 1 -maxdepth 1 \
    ! -name 'backend' \
    ! -name 'logs' \
    -exec rm -rf {} +
fi

sudo tar -xzf "$ARCHIVE_PATH" -C "$TARGET_DIR" --strip-components=1

cd "$TARGET_DIR"
if [[ ! -f "$TARGET_DIR/backend/.env" ]]; then
  cp "$TARGET_DIR/backend/.env.example" "$TARGET_DIR/backend/.env"
  echo "created $TARGET_DIR/backend/.env from template, please edit it and rerun installer" >&2
  exit 1
fi
WEB_ADMIN_SKIP_FRONTEND_BUILD=true ./deploy.sh prepare

sed \
  -e "s|__TARGET_DIR__|${TARGET_DIR}|g" \
  -e "s|__SERVICE_USER__|${SERVICE_USER}|g" \
  "$TARGET_DIR/web-admin.service" | sudo tee "$SERVICE_PATH" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager || true
