#!/bin/bash
# One-time: copy your local database, FIT files and Garmin tokens to the instance.
# Uploads to the private backup bucket (import/ prefix), then pulls them into /data.
# Usage: infra/scripts/migrate-data.sh [local-data-dir] [garmin-token-dir]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DATA_DIR="${1:-$REPO_ROOT/data}"
GARMIN_DIR="${2:-$HOME/.soft-floyd/garmin}"
BUCKET="$(out backup_bucket)"
DB="soft-floyd-accounts.db"

read -r -p "This REPLACES the database on the server with $DATA_DIR/$DB. Continue? [y/N] " yn
[ "$yn" = "y" ] || exit 1

snapshot="$(mktemp -d)"
trap 'rm -rf "$snapshot"' EXIT
sqlite3 "$DATA_DIR/$DB" ".backup '$snapshot/$DB'"

aws s3 cp "$snapshot/$DB" "s3://$BUCKET/import/$DB"
[ -d "$DATA_DIR/fit" ] && aws s3 sync "$DATA_DIR/fit" "s3://$BUCKET/import/fit"
[ -d "$GARMIN_DIR" ] && aws s3 sync "$GARMIN_DIR" "s3://$BUCKET/import/garmin"

run_remote "set -e
systemctl stop soft-floyd
aws s3 cp s3://$BUCKET/import/$DB /data/$DB
aws s3 sync s3://$BUCKET/import/fit /data/fit || true
aws s3 sync s3://$BUCKET/import/garmin /data/garmin || true
rm -f /data/$DB-wal /data/$DB-shm
chown -R 1000:1000 /data
systemctl start soft-floyd"
