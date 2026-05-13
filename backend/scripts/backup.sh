#!/bin/bash
# WorkspaceOS database backup script
# Runs pg_dump and saves to /app/backend_data/backups/
# Keeps the last 7 daily backups

set -e

BACKUP_DIR="/app/backend_data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="workspaceos_${TIMESTAMP}.sql.gz"

# Extract DB credentials from DATABASE_URL
# Format: postgresql+asyncpg://user:pass@host:port/dbname
DB_URL="${DATABASE_URL:-postgresql+asyncpg://pr_secretary:pr_secretary@db:5432/pr_secretary}"
# Strip the driver prefix
DB_URL="${DB_URL#*://}"
DB_USER="${DB_URL%%:*}"
DB_URL="${DB_URL#*:}"
DB_PASS="${DB_URL%%@*}"
DB_URL="${DB_URL#*@}"
DB_HOST="${DB_URL%%:*}"
DB_URL="${DB_URL#*:}"
DB_PORT="${DB_URL%%/*}"
DB_NAME="${DB_URL#*/}"

mkdir -p "$BACKUP_DIR"

echo "Starting backup: $FILENAME (db=$DB_NAME@$DB_HOST:$DB_PORT)"
PGPASSWORD="$DB_PASS" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$FILENAME"

SIZE=$(du -h "$BACKUP_DIR/$FILENAME" | cut -f1)
echo "Backup complete: $BACKUP_DIR/$FILENAME ($SIZE)"

# Rotate: keep only the last 7 backups
cd "$BACKUP_DIR"
ls -t workspaceos_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm
COUNT=$(ls workspaceos_*.sql.gz 2>/dev/null | wc -l)
echo "Retained backups: $COUNT"

# Also backup the Fernet encryption key (needed to decrypt app_settings)
FERNET_KEY="/app/backend_data/fernet.key"
if [ -f "$FERNET_KEY" ]; then
    cp "$FERNET_KEY" "$BACKUP_DIR/fernet_${TIMESTAMP}.key"
    echo "Fernet key backed up"
    # Rotate: keep only last 7 fernet key backups
    ls -t "$BACKUP_DIR"/fernet_*.key 2>/dev/null | tail -n +8 | xargs -r rm
fi
