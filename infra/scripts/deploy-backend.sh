#!/bin/bash
# Build the arm64 image, push it to ECR and restart the service on the instance.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

REPO_URL="$(out ecr_repo_url)"
REGION="$(out region)"
SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO_URL%%/*}"

docker buildx build --platform linux/arm64 \
  -t "$REPO_URL:latest" -t "$REPO_URL:$SHA" --push "$REPO_ROOT"

run_remote "systemctl restart soft-floyd && sleep 20 && docker exec soft-floyd python -c \"import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read())\""
