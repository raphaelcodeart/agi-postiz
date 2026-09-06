#!/usr/bin/env bash
# Redeploys the stack after pulling new code: rebuilds changed images, applies any
# new Alembic migrations, then restarts services with zero manual steps.
#
# Usage (from the repository root, on the server):
#   ./scripts/deploy.sh            # uses docker-compose.prod.yml
#   COMPOSE_FILE=docker-compose.yml ./scripts/deploy.sh   # dev stack instead
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

echo "==> Pulling latest code (git pull)"
git pull

echo "==> Building images (${COMPOSE_FILE})"
docker compose -f "${COMPOSE_FILE}" build

echo "==> Starting db and redis first, waiting until healthy"
docker compose -f "${COMPOSE_FILE}" up -d db redis
for i in $(seq 1 30); do
  if docker compose -f "${COMPOSE_FILE}" ps db | grep -q "healthy"; then
    break
  fi
  sleep 2
done

echo "==> Applying database migrations"
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head

echo "==> Starting all services"
docker compose -f "${COMPOSE_FILE}" up -d

# Nginx caches the resolved IP of upstream containers (api/dashboard) and doesn't
# notice on its own when they get recreated with a new image - reload picks up
# the new addresses. A no-op if nginx isn't part of this compose file's services.
if docker compose -f "${COMPOSE_FILE}" ps nginx >/dev/null 2>&1; then
  echo "==> Reloading nginx to pick up any recreated upstream containers"
  docker compose -f "${COMPOSE_FILE}" exec nginx nginx -s reload || true
fi

echo "==> Done. Current status:"
docker compose -f "${COMPOSE_FILE}" ps
