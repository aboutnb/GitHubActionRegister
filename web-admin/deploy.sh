#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-deploy}"

if [[ "$COMMAND" == "--pull" ]]; then
  git -C "$ROOT_DIR" pull --ff-only
  COMMAND="deploy"
fi

cd "$ROOT_DIR"
python3 deploy.py "$COMMAND"
