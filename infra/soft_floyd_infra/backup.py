"""Private S3 bucket for nightly backups and one-time data imports."""

import pulumi_aws as aws


def backup_bucket() -> aws.s3.Bucket:
    bucket = aws.s3.Bucket("backup")
    aws.s3.BucketPublicAccessBlock(
        "backup-public-block",
        bucket=bucket.id,
        block_public_acls=True,
        block_public_policy=True,
        ignore_public_acls=True,
        restrict_public_buckets=True,
    )
    aws.s3.BucketServerSideEncryptionConfiguration(
        "backup-sse",
        bucket=bucket.id,
        rules=[{"apply_server_side_encryption_by_default": {"sse_algorithm": "AES256"}}],
    )
    aws.s3.BucketLifecycleConfiguration(
        "backup-lifecycle",
        bucket=bucket.id,
        rules=[
            {
                "id": "expire-old-backups",
                "status": "Enabled",
                "filter": {"prefix": ""},
                "expiration": {"days": 30},
                "abort_incomplete_multipart_upload": {"days_after_initiation": 7},
            }
        ],
    )
    return bucket
