#!/usr/bin/env bash

set -euo pipefail

REPO="__REPO__"
TARGET_DIR="${WEB_ADMIN_TARGET_DIR:-/opt/web-admin}"
TMP_DIR="${TMPDIR:-/tmp}"

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
WEB_ADMIN_SKIP_FRONTEND_BUILD=true ./deploy.sh
