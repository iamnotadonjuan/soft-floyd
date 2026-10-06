"""Soft Floyd on AWS: S3 + CloudFront UI, one small EC2 box for the backend."""

import pulumi
import pulumi_aws as aws
import pulumi_random as random
from soft_floyd_infra.backend import Backend
from soft_floyd_infra.backup import backup_bucket
from soft_floyd_infra.secrets import parameters
from soft_floyd_infra.web import Web

config = pulumi.Config()

origin_verify = random.RandomPassword("origin-verify", length=40, special=False)
jwt_secret = random.RandomPassword("jwt-secret", length=64, special=False)

backups = backup_bucket()
backend = Backend(
    instance_type=config.get("instanceType") or "t4g.nano",
    data_volume_gb=config.get_int("dataVolumeGb") or 2,
    backup_bucket=backups,
    # Filled in below; the instance only needs them to exist before first boot.
    parameter_deps=[],
)
web = Web(
    origin_domain=backend.eip.public_dns,
    origin_verify_secret=origin_verify.result,
)

base_url = web.domain.apply(lambda d: f"https://{d}")
param_resources = parameters(
    {
        "openai_api_key": config.require_secret("openaiApiKey"),
        "google_client_id": config.require_secret("googleClientId"),
        "google_client_secret": config.require_secret("googleClientSecret"),
        "jwt_secret": jwt_secret.result,
        "origin_verify_secret": origin_verify.result,
        "web_origin": base_url,
        "google_redirect_uri": base_url.apply(lambda u: f"{u}/api/auth/google/callback"),
        "cookie_secure": "true",
        "llm_monthly_budget_usd": config.get("llmMonthlyBudgetUsd") or "10",
        # The server talks to its own /mcp over loopback inside the container.
        "internal_mcp_url": "http://127.0.0.1:8000/mcp",
    },
    secret_keys={
        "openai_api_key",
        "google_client_id",
        "google_client_secret",
        "jwt_secret",
        "origin_verify_secret",
    },
)
backend.parameter_deps = param_resources
instance = backend.create_instance()

pulumi.export("cf_url", base_url)
pulumi.export("distribution_id", web.distribution.id)
pulumi.export("web_bucket", web.bucket.bucket)
pulumi.export("backup_bucket", backups.bucket)
pulumi.export("ecr_repo_url", backend.repo.repository_url)
pulumi.export("instance_id", instance.id)
pulumi.export("origin_dns", backend.eip.public_dns)
pulumi.export("region", aws.get_region().region)
pulumi.export(
    "google_redirect_uri",
    base_url.apply(lambda u: f"{u}/api/auth/google/callback"),
)
