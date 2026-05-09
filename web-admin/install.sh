#!/usr/bin/env bash

set -euo pipefail

REPO="__REPO__"
TARGET_DIR="${WEB_ADMIN_TARGET_DIR:-/opt/web-admin}"
TMP_DIR="${TMPDIR:-/tmp}"
SERVICE_NAME="${WEB_ADMIN_SERVICE_NAME:-web-admin}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_USER="${WEB_ADMIN_SERVICE_USER:-$(id -un)}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "install-web-admin.sh only supports Linux." >&2
  exit 1
fi

ARCH_NAME="$(uname -m)"

case "$ARCH_NAME" in
  x86_64|amd64)
    ARCH_TAG="amd64"
    ;;
  aarch64|arm64)
    ARCH_TAG="arm64"
    ;;
  *)
    echo "unsupported Linux architecture: $ARCH_NAME" >&2
    exit 1
    ;;
esac

ARCHIVE_NAME="web-admin-linux-${ARCH_TAG}.tar.gz"
ARCHIVE_URL="https://github.com/${REPO}/releases/latest/download/${ARCHIVE_NAME}"
ARCHIVE_PATH="${TMP_DIR}/${ARCHIVE_NAME}"

curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
sudo mkdir -p "$(dirname "$TARGET_DIR")"
sudo mkdir -p "$TARGET_DIR"

if [[ -d "$TARGET_DIR/backend" ]]; then
  sudo find "$TARGET_DIR/backend" -mindepth 1 -maxdepth 1 \
    ! -name '.env' \
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
  sudo cp "$TARGET_DIR/backend/.env.example" "$TARGET_DIR/backend/.env"
  echo "created $TARGET_DIR/backend/.env from template, please edit it and rerun installer" >&2
  exit 1
fi

"$TARGET_DIR/backend/runtime/web-admin-backend" prepare

sed \
  -e "s|__TARGET_DIR__|${TARGET_DIR}|g" \
  -e "s|__SERVICE_USER__|${SERVICE_USER}|g" \
  "$TARGET_DIR/web-admin.service" | sudo tee "$SERVICE_PATH" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager || true
