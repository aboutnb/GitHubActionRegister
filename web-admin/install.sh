#!/usr/bin/env bash

set -euo pipefail

TARGET_DIR="${WEB_ADMIN_TARGET_DIR:-/opt/web-admin}"
IMAGE="${WEB_ADMIN_IMAGE:-__IMAGE__}"
CONTAINER_NAME="${WEB_ADMIN_CONTAINER_NAME:-web-admin}"
SKIP_PULL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-dir)
      TARGET_DIR="$2"
      shift 2
      ;;
    --image)
      IMAGE="$2"
      shift 2
      ;;
    --database-url)
      WEB_ADMIN_DATABASE_URL="$2"
      shift 2
      ;;
    --jwt-secret)
      WEB_ADMIN_JWT_SECRET="$2"
      shift 2
      ;;
    --encrypt-secret)
      WEB_ADMIN_ENCRYPT_SECRET="$2"
      shift 2
      ;;
    --admin-password)
      WEB_ADMIN_ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --database-bootstrap)
      WEB_ADMIN_DATABASE_BOOTSTRAP="$2"
      shift 2
      ;;
    --database-admin-url)
      WEB_ADMIN_DATABASE_ADMIN_URL="$2"
      shift 2
      ;;
    --database-admin-database)
      WEB_ADMIN_DATABASE_ADMIN_DATABASE="$2"
      shift 2
      ;;
    --admin-username)
      WEB_ADMIN_ADMIN_USERNAME="$2"
      shift 2
      ;;
    --port)
      WEB_ADMIN_PORT="$2"
      shift 2
      ;;
    --workers)
      WEB_ADMIN_WORKERS="$2"
      shift 2
      ;;
    --log-level)
      WEB_ADMIN_LOG_LEVEL="$2"
      shift 2
      ;;
    --cookie-secure)
      WEB_ADMIN_COOKIE_SECURE="$2"
      shift 2
      ;;
    --container-name)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --skip-pull)
      SKIP_PULL=true
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ENV_PATH="${TARGET_DIR}/backend/.env"
COMPOSE_PATH="${TARGET_DIR}/docker-compose.yml"
DEFAULT_ADMIN_PASSWORD="admin123456"
DEFAULT_SERVICE_PORT="18700"

OS_NAME="$(uname -s)"
if [[ "$OS_NAME" != "Linux" && "$OS_NAME" != "Darwin" ]]; then
  echo "install-web-admin.sh only supports Linux and macOS." >&2
  exit 1
fi

TARGET_PARENT="$(dirname "$TARGET_DIR")"
declare -a ROOT_PREFIX=()
if [[ "${EUID}" -eq 0 ]]; then
  :
elif [[ -d "$TARGET_DIR" && -w "$TARGET_DIR" ]]; then
  :
elif [[ -d "$TARGET_PARENT" && -w "$TARGET_PARENT" ]]; then
  :
elif command -v sudo >/dev/null 2>&1; then
  ROOT_PREFIX=(sudo)
else
  echo "this installer needs root access (run as root or install sudo)" >&2
  exit 1
fi

as_root() {
  if [[ ${#ROOT_PREFIX[@]} -eq 0 ]]; then
    "$@"
  else
    "${ROOT_PREFIX[@]}" "$@"
  fi
}

generate_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print $2}' "$ENV_PATH" | tail -n 1 | tr -d '"' | tr -d "'" | tr -d '\r' | tr -d '[:space:]'
}

write_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 {
      if (!replaced) {
        print key "=" value
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) {
        print key "=" value
      }
    }
  ' "$ENV_PATH" > "$tmp_file"
  as_root cp "$tmp_file" "$ENV_PATH"
  rm -f "$tmp_file"
}

ensure_env_default() {
  local key="$1"
  local value="$2"
  local current_value
  current_value="$(read_env_value "$key")"
  if [[ -z "$current_value" ]]; then
    write_env_value "$key" "$value"
  fi
}

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  DOCKER_CMD="docker"
elif command -v docker >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
  DOCKER_CMD="sudo docker"
else
  echo "docker is required but was not found or is not usable" >&2
  exit 1
fi

if ${DOCKER_CMD} compose version >/dev/null 2>&1; then
  COMPOSE_CMD="${DOCKER_CMD} compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
elif command -v docker-compose >/dev/null 2>&1 && sudo docker-compose version >/dev/null 2>&1; then
  COMPOSE_CMD="sudo docker-compose"
else
  echo "docker compose is required but was not found" >&2
  exit 1
fi

as_root mkdir -p "$TARGET_DIR/backend"
as_root mkdir -p "$TARGET_DIR"

if [[ ! -f "$ENV_PATH" ]]; then
  if [[ -n "${WEB_ADMIN_DATABASE_URL:-}" ]]; then
    JWT_SECRET_VALUE="${WEB_ADMIN_JWT_SECRET:-$(generate_secret)}"
    ENCRYPT_SECRET_VALUE="${WEB_ADMIN_ENCRYPT_SECRET:-$(generate_secret)}"
    ADMIN_PASSWORD_VALUE="${WEB_ADMIN_ADMIN_PASSWORD:-$DEFAULT_ADMIN_PASSWORD}"
    PORT_VALUE="${WEB_ADMIN_PORT:-$DEFAULT_SERVICE_PORT}"
    cat <<EOF | as_root tee "$ENV_PATH" >/dev/null
WEB_ADMIN_DATABASE_URL=${WEB_ADMIN_DATABASE_URL}
WEB_ADMIN_JWT_SECRET=${JWT_SECRET_VALUE}
WEB_ADMIN_ENCRYPT_SECRET=${ENCRYPT_SECRET_VALUE}
WEB_ADMIN_ADMIN_PASSWORD=${ADMIN_PASSWORD_VALUE}
WEB_ADMIN_PORT=${PORT_VALUE}
EOF

    for key in \
      WEB_ADMIN_DATABASE_BOOTSTRAP \
      WEB_ADMIN_DATABASE_ADMIN_URL \
      WEB_ADMIN_DATABASE_ADMIN_DATABASE \
      WEB_ADMIN_ADMIN_USERNAME \
      WEB_ADMIN_WORKERS \
      WEB_ADMIN_LOG_LEVEL \
      WEB_ADMIN_COOKIE_SECURE
    do
      value="${!key:-}"
      if [[ -n "$value" ]]; then
        echo "${key}=${value}" | as_root tee -a "$ENV_PATH" >/dev/null
      fi
    done
  else
    cat <<'EOF' | as_root tee "$ENV_PATH" >/dev/null
WEB_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:123456@127.0.0.1:5432/github_asset_center
WEB_ADMIN_JWT_SECRET=
WEB_ADMIN_ENCRYPT_SECRET=
WEB_ADMIN_ADMIN_PASSWORD=admin123456
WEB_ADMIN_PORT=18700

# Optional: database bootstrap
# WEB_ADMIN_DATABASE_BOOTSTRAP=false

# Optional: use a separate admin connection for automatic database creation
# WEB_ADMIN_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:123456@127.0.0.1:5432/postgres
# WEB_ADMIN_DATABASE_ADMIN_DATABASE=postgres

# Optional: service overrides
# WEB_ADMIN_WORKERS=1
# WEB_ADMIN_LOG_LEVEL=info
# WEB_ADMIN_COOKIE_SECURE=true
EOF
    echo "created ${ENV_PATH}, please edit it and rerun installer" >&2
    echo "default admin credentials: admin / admin123456" >&2
    echo "default service port: 18700" >&2
    echo "jwt / encrypt secret can stay empty in the template; the installer will auto-generate them on deploy" >&2
    echo "or rerun with bash arguments such as --database-url for true one-shot setup" >&2
    exit 1
  fi
fi

ensure_env_default "WEB_ADMIN_JWT_SECRET" "$(generate_secret)"
ensure_env_default "WEB_ADMIN_ENCRYPT_SECRET" "$(generate_secret)"
ensure_env_default "WEB_ADMIN_ADMIN_PASSWORD" "$DEFAULT_ADMIN_PASSWORD"
ensure_env_default "WEB_ADMIN_PORT" "$DEFAULT_SERVICE_PORT"

SERVICE_PORT="$(read_env_value "WEB_ADMIN_PORT")"
if [[ -z "$SERVICE_PORT" ]]; then
  SERVICE_PORT="$DEFAULT_SERVICE_PORT"
fi

cat <<EOF | as_root tee "$COMPOSE_PATH" >/dev/null
services:
  web-admin:
    image: ${IMAGE}
    container_name: ${CONTAINER_NAME}
    restart: unless-stopped
    ports:
      - "${SERVICE_PORT}:${SERVICE_PORT}"
    env_file:
      - ${ENV_PATH}
EOF

if [[ "$SKIP_PULL" != "true" ]]; then
  ${DOCKER_CMD} pull "$IMAGE"
fi
${COMPOSE_CMD} -f "$COMPOSE_PATH" up -d

echo "waiting for ${CONTAINER_NAME} to become healthy..."
for _ in $(seq 1 30); do
  status="$(${DOCKER_CMD} inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
  if [[ "$status" == "healthy" || "$status" == "running" ]]; then
    echo "web-admin is ready: http://127.0.0.1:${SERVICE_PORT}"
    ${COMPOSE_CMD} -f "$COMPOSE_PATH" ps
    exit 0
  fi
  sleep 2
done

echo "web-admin did not become ready in time. Recent logs:" >&2
${DOCKER_CMD} logs --tail 100 "${CONTAINER_NAME}" >&2 || true
exit 1
