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

## Copy the training books

The server starts with no books, so coach answers cite nothing until some are added.
To copy the ones you already imported locally (embeddings included, so no new OpenAI
spend) without touching anything else on the server:

```bash
make deploy-backend              # the image needs the `soft-floyd books copy` command
infra/scripts/copy-books.sh      # prints "Added N books (M passages); K already present."
```

It is safe to rerun: books are matched by hash, so a second run adds nothing.

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

## CI/CD

`.github/workflows/ci.yml` runs on every PR to `main` and every push to `main`:
ESLint + `tsc` for `apps/web`, then ruff (check + format) and pytest. A push to
`main` that passes all of them calls `.github/workflows/deploy.yml` (the same
three steps as above). `deploy.yml` can also be run by hand from the Actions tab.

The deploy job is skipped, not failed, until the `AWS_ROLE_ARN` repository
variable exists. One-time setup:

1. Run `infra/scripts/bootstrap-github-oidc.sh` with admin AWS credentials. It
   creates the GitHub OIDC identity provider and an IAM role that only the
   `production` environment of `iamnotadonjuan/soft-floyd` can assume (the
   deploy job uses that environment), and prints the role ARN.
2. The role gets `AdministratorAccess` because Pulumi creates IAM roles,
   instances, buckets and CloudFront; the trust policy is what restricts it.
   Narrow it later if you want.
3. Set repository variables `AWS_ROLE_ARN` and `PULUMI_BACKEND_URL`, and
   secret `PULUMI_CONFIG_PASSPHRASE`.
4. Optional: add protection rules to the `production` environment, and require
   the `CI` checks on `main` in branch protection.
