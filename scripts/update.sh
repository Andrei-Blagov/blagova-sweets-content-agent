#!/usr/bin/env bash
# Hourly auto-update for BLAGOVA_SWEETS Content Agent.
# Pulls from GitHub and rebuilds Docker Compose only when new commits appear.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/projects/blagova-sweets-content-agent}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BRANCH="${BRANCH:-main}"
LOG_DIR="${LOG_DIR:-/home/andrei/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/blagova-sweets-content-agent-update.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/update-blagova-sweets-content-agent.lock}"
REMOTE="${REMOTE:-origin}"

mkdir -p "$LOG_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  COMPOSE_CMD=(docker-compose)
fi

log() {
  echo "[$(date -Is)] $*" | tee -a "$LOG_FILE"
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Skip: another update is already running"
  exit 0
fi

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  log "ERROR: git repo not found: $PROJECT_DIR"
  exit 1
fi

cd "$PROJECT_DIR"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  log "Skip: .env not found yet (project not fully deployed). Repo left untouched."
  exit 0
fi

if [[ ! -f "$PROJECT_DIR/$COMPOSE_FILE" ]]; then
  log "ERROR: compose file not found: $PROJECT_DIR/$COMPOSE_FILE"
  exit 1
fi

log "=== Checking updates ($REMOTE/$BRANCH) ==="

git fetch --prune "$REMOTE" "$BRANCH" >>"$LOG_FILE" 2>&1

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "$REMOTE/$BRANCH")"

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  log "Already up to date ($LOCAL_SHA). Ensuring containers are up."
  "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d >>"$LOG_FILE" 2>&1
  log "=== Done (no code changes) ==="
  exit 0
fi

log "New commits detected: $LOCAL_SHA -> $REMOTE_SHA"
git pull --ff-only "$REMOTE" "$BRANCH" >>"$LOG_FILE" 2>&1

log "Rebuilding and restarting containers..."
"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d --build >>"$LOG_FILE" 2>&1

# Optional health wait (API service)
APP_PORT="$(grep -E '^APP_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || true)"
APP_PORT="${APP_PORT:-8090}"
if command -v curl >/dev/null 2>&1; then
  for _ in 1 2 3 4 5 6; do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
      log "Health OK on :${APP_PORT}"
      break
    fi
    sleep 5
  done
fi

log "=== Update complete ($REMOTE_SHA) ==="
