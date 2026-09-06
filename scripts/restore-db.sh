#!/usr/bin/env bash
# Restores a SQL dump created by backup-db.sh into the running PostgreSQL container.
# DESTRUCTIVE: this overwrites the current database content for the tables in the dump.
#
# Usage:
#   ./scripts/restore-db.sh backups/latest.sql
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP_FILE="${1:-}"
if [ -z "${DUMP_FILE}" ] || [ ! -f "${DUMP_FILE}" ]; then
  echo "Usage: $0 <path-to-dump.sql>"
  echo "Example: $0 backups/latest.sql"
  exit 1
fi

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

echo "About to restore '${DUMP_FILE}' into database '${POSTGRES_DB}' (service '${DB_SERVICE}')."
echo "This will DROP and recreate existing objects found in the dump."
read -r -p "Type 'yes' to continue: " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "${DUMP_FILE}"

echo "Restore complete. Restart the api/worker/beat services to be safe:"
echo "  docker compose -f ${COMPOSE_FILE} restart api worker beat"
