# 0017 — AWS deployment (cheap, Pulumi)

## Context

Soft Floyd only ran on localhost. Goal: host it on AWS for the least money,
with every resource defined as Pulumi code in `infra/` so GitHub Actions can
deploy it later. Target cost is about $7.5/month.

The backend is stateful (SQLite incl. book embeddings, Garmin token dirs, FIT
files, an always-on Garmin poller, SSE chat, loopback `/mcp` call). Lambda
would need EFS in a VPC plus a NAT gateway (~$32/mo) to reach OpenAI/Garmin,
or a DB rewrite. So: one small EC2 box, same code, same SQLite.

Done means: the UI loads from the CloudFront URL, Google sign-in works,
Garmin sync and coach chat work, and nightly backups land in S3.

## Design

```
Browser -> CloudFront (*.cloudfront.net, free HTTPS)
  default  -> S3 web bucket (private, OAC) + CF Function SPA rewrite
  /api/*, /mcp* -> EC2 t4g.nano :8000 (CachingDisabled, X-Origin-Verify header)
EC2: Docker image from ECR, /data on a separate protected EBS volume,
     SG allows only the CloudFront origin-facing prefix list, SSM (no SSH),
     secrets from SSM Parameter Store, nightly backup to S3.
```

- The app stays same-origin, so the cookie JWT and the Origin check in
  `auth_middleware.py` work unchanged; only env config differs.
- `SOFT_FLOYD_ORIGIN_VERIFY_SECRET` makes the server reject requests that
  lack the `X-Origin-Verify` header CloudFront adds, so the origin cannot be
  reached through anyone else's distribution. Unset locally, so it is a no-op.
- Pulumi in Python, own uv project in `infra/`, state in an S3 backend.

## Steps

1. `origin_verify_secret` setting + `OriginVerifyMiddleware` + test.
2. `Dockerfile`, `.dockerignore`.
3. `infra/` Pulumi program, user-data, deploy and migration scripts.
4. `Makefile` targets, `.github/workflows/deploy.yml` (manual trigger only).
5. Update `ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/RELIABILITY.md`, `AGENTS.md`.

## Verification

- `make check`.
- `docker build --platform linux/arm64 .`; with the secret set, `/api/health`
  is 403 without the header and 200 with it.
- `pulumi preview`, then `pulumi up`; deploy scripts; SPA, deep link,
  `/api/health`, direct EC2:8000 blocked.
- Google sign-in, Garmin sync, coach streaming, manual backup run.

## Deferred / risks

- Garmin may throttle datacenter IPs; fallback is a local `garmin-login` and
  uploading the token dir with `infra/scripts/migrate-data.sh`.
- 512MB RAM: swap added; move to `t4g.micro` if the coach or PDF import OOMs.
- Custom domain, WAF, multi-AZ are not included. CI activation moved to 0019-ci-cd.
