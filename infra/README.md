# Soft Floyd on AWS

About $7.5/month: one `t4g.nano` instance (server + SQLite on a small EBS
volume), an S3 bucket for the UI, and CloudFront in front of both. The app is
served from the free `https://xxxx.cloudfront.net` URL.

```
Browser -> CloudFront
  /            -> S3 web bucket (private, origin access control)
  /api/*, /mcp* -> EC2 :8000 (security group: CloudFront only; header X-Origin-Verify)
EC2: Docker image from ECR, /data on a protected EBS volume, secrets in SSM
     Parameter Store, nightly backup to S3 (30 days), managed through SSM (no SSH)
```

Design and trade-offs: `docs/exec-plans/active/0017-aws-deployment.md`.

## One-time setup

Needs the AWS CLI (credentials with admin-ish rights), Pulumi, uv, pnpm and
Docker with buildx.

```bash
infra/scripts/bootstrap-state.sh          # creates the state bucket, prints the login command
export PULUMI_CONFIG_PASSPHRASE='...'     # keep it; it encrypts the stack's secrets
pulumi login s3://soft-floyd-pulumi-state-<account-id>

cd infra
uv sync
pulumi stack init prod
pulumi config set --secret openaiApiKey sk-...
pulumi config set --secret googleClientId ...apps.googleusercontent.com
pulumi config set --secret googleClientSecret ...
pulumi up
```

`pulumi up` prints `google_redirect_uri`. Add it to the **Authorized redirect
URIs** of your Google OAuth client (the web-app one you use locally).

## Deploy

```bash
make deploy-backend    # build arm64 image -> ECR -> restart service, checks /api/health
make deploy-web        # build UI -> S3 -> CloudFront invalidation
```

The first `pulumi up` boots the instance before any image exists, so the
service keeps retrying until the first `make deploy-backend`.

## Bring your existing data

```bash
infra/scripts/migrate-data.sh
```

Copies `data/soft-floyd-accounts.db` (snapshotted with `sqlite3 .backup`),
`data/fit` and `~/.soft-floyd/garmin` to the server. Garmin may throttle logins
from AWS addresses, so log in locally with `soft-floyd garmin-login` first and
migrate the token directory rather than logging in from the server.

## Operations

- Shell on the box: `aws ssm start-session --target $(cd infra && pulumi stack output instance_id)`
- Logs: `journalctl -u soft-floyd -f` (inside that session)
- Manual backup: `systemctl start soft-floyd-backup`; objects land in
  `s3://<backup_bucket>/db/` and `/files/`.
- Restore: stop the service, `aws s3 cp` the chosen `db/<date>.db.gz` from the
  backup bucket, `gunzip` it to `/data/soft-floyd-accounts.db`, start the service.
- Out of memory (coach, PDF import): `pulumi config set instanceType t4g.micro` and `pulumi up`.
  The data volume is protected and re-attaches to the new instance.
- Tear down: `pulumi destroy` fails on purpose while the data volume is protected.
  Back up first, then `pulumi state unprotect` it.

## CI later

`.github/workflows/deploy.yml` runs the same three steps from GitHub Actions
(manual trigger for now). Create an AWS role that trusts your repository's
GitHub OIDC token, then set repository variables `AWS_ROLE_ARN` and
`PULUMI_BACKEND_URL` and secret `PULUMI_CONFIG_PASSPHRASE`.
