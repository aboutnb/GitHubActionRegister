#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--pull" ]]; then
  git -C "$ROOT_DIR" pull --ff-only
fi

cd "$ROOT_DIR"
python3 deploy.py
