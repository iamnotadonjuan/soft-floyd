#!/bin/bash
# Add your local training books (with their embeddings) to the server's database.
# Only the book tables are read; the server's accounts, sessions and rides are untouched,
# and rerunning adds nothing. Needs a backend image that has `soft-floyd books copy`
# (run `make deploy-backend` first).
# Usage: infra/scripts/copy-books.sh [local-db]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DB="${1:-$REPO_ROOT/data/soft-floyd-accounts.db}"
BUCKET="$(out backup_bucket)"
KEY="import/books-source.db"

snapshot="$(mktemp -d)"
# The snapshot holds your whole local database: never leave it behind, even on failure.
cleanup() {
  rm -rf "$snapshot"
  aws s3 rm "s3://$BUCKET/$KEY" >/dev/null 2>&1 || true
}
trap cleanup EXIT
sqlite3 "$DB" ".backup '$snapshot/books-source.db'"

aws s3 cp "$snapshot/books-source.db" "s3://$BUCKET/$KEY"

# The container sees /data, so stage the snapshot there for the command.
run_remote "set -e
trap 'rm -rf /data/import' EXIT
mkdir -p /data/import
aws s3 cp s3://$BUCKET/$KEY /data/import/books-source.db
chown -R 1000:1000 /data/import
docker exec soft-floyd soft-floyd books copy --source /data/import/books-source.db"
