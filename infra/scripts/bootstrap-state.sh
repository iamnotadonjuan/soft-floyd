#!/bin/bash
# One-time: create the S3 bucket that holds Pulumi state, then log in to it.
# Usage: infra/scripts/bootstrap-state.sh [region]
set -euo pipefail

REGION="${1:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="soft-floyd-pulumi-state-$ACCOUNT"

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket $BUCKET already exists."
else
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION"
  fi
  aws s3api put-bucket-versioning --bucket "$BUCKET" \
    --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

echo
echo "Next:"
echo "  export PULUMI_CONFIG_PASSPHRASE='<choose one and keep it>'"
echo "  pulumi login s3://$BUCKET"
echo "  cd infra && pulumi stack init prod   # first time only"
