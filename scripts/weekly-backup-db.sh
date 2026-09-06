#!/usr/bin/env bash
# Full weekly database backup (schema + data), kept LOCAL ONLY - never pushed
# to git (see .gitignore). Distinct from scripts/backup-db.sh (ad-hoc dumps in
# backups/, taken manually before a risky deploy): this one is meant to run
# unattended on a schedule (see the cron job installed alongside it) and
# prunes old backups itself so the folder doesn't grow forever.
#
# Usage (from the repository root, on the server):
#   ./scripts/weekly-backup-db.sh
#   COMPOSE_FILE=docker-compose.yml ./scripts/weekly-backup-db.sh   # dev stack instead
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
KEEP_WEEKS="${KEEP_WEEKS:-12}"
OUT_DIR="weekly-backup-db"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-social_publisher}"

mkdir -p "${OUT_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTFILE="${OUT_DIR}/weekly_${TIMESTAMP}.sql.gz"

echo "Dumping database '${POSTGRES_DB}' from service '${DB_SERVICE}' (compose file: ${COMPOSE_FILE})..."

docker compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists | gzip > "${OUTFILE}"

cp "${OUTFILE}" "${OUT_DIR}/latest.sql.gz"

echo "Done: ${OUTFILE}"

# Retention: keep only the most recent KEEP_WEEKS timestamped dumps (latest.sql.gz
# is a copy, not counted, and never deleted here).
mapfile -t OLD_BACKUPS < <(ls -1t "${OUT_DIR}"/weekly_*.sql.gz 2>/dev/null | tail -n +$((KEEP_WEEKS + 1)))
if [ "${#OLD_BACKUPS[@]}" -gt 0 ]; then
  echo "Pruning ${#OLD_BACKUPS[@]} backup(s) older than the last ${KEEP_WEEKS}:"
  printf '  %s\n' "${OLD_BACKUPS[@]}"
  rm -f "${OLD_BACKUPS[@]}"
fi

echo ""
echo "These backups are local-only (excluded from git, see .gitignore) - copy"
echo "them off this server periodically if you want protection against losing"
echo "the server itself, not just the database."
