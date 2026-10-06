#!/bin/bash
# Build the web app, upload it to the web bucket and invalidate CloudFront.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

BUCKET="$(out web_bucket)"
DISTRIBUTION="$(out distribution_id)"

cd "$REPO_ROOT"
pnpm install --frozen-lockfile
pnpm --filter soft-floyd-web build

DIST="$REPO_ROOT/apps/web/dist"
# Hashed assets can be cached forever; everything else must revalidate.
aws s3 sync "$DIST" "s3://$BUCKET" --delete --exclude "assets/*" \
  --cache-control "no-cache"
aws s3 sync "$DIST/assets" "s3://$BUCKET/assets" --delete \
  --cache-control "public,max-age=31536000,immutable"

aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION" --paths "/*" >/dev/null
echo "Deployed to $(out cf_url)"
