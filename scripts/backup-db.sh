#!/usr/bin/env bash
# Creates a full SQL dump of the PostgreSQL database used by the platform.
# Run this from the repository root, on the server, with the stack already running:
#   ./scripts/backup-db.sh
#
# The dump is written to backups/<timestamp>.sql and also updated as backups/latest.sql
# so restore scripts and documentation can always point at a stable filename.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-social_publisher}"

mkdir -p backups
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTFILE="backups/${TIMESTAMP}.sql"

echo "Dumping database '${POSTGRES_DB}' from service '${DB_SERVICE}' (compose file: ${COMPOSE_FILE})..."

docker compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists > "${OUTFILE}"

cp "${OUTFILE}" backups/latest.sql

echo "Done."
echo "  Full dump: ${OUTFILE}"
echo "  Shortcut:  backups/latest.sql"
echo ""
echo "Keep these files outside the server too (e.g. download them) - they are the only"
echo "backup of production data. They are excluded from git via .gitignore."
