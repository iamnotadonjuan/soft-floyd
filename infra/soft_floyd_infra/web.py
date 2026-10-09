"""Static UI in a private S3 bucket behind CloudFront.

CloudFront also forwards /api/* and /mcp* to the EC2 origin so the browser
only ever talks to one HTTPS origin (cookies and the Origin check keep
working unchanged).
"""

import json

import pulumi
import pulumi_aws as aws

# AWS managed policies, looked up by name so no ids are hard-coded.
CACHING_OPTIMIZED = aws.cloudfront.get_cache_policy(name="Managed-CachingOptimized").id
CACHING_DISABLED = aws.cloudfront.get_cache_policy(name="Managed-CachingDisabled").id
ALL_VIEWER_EXCEPT_HOST = aws.cloudfront.get_origin_request_policy(
    name="Managed-AllViewerExceptHostHeader"
).id

SPA_REWRITE = """function handler(event) {
  var request = event.request;
  if (request.uri.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
"""

UI_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


class Web:
    def __init__(
        self,
        origin_domain: pulumi.Input[str],
        origin_verify_secret: pulumi.Input[str],
    ) -> None:
        self.bucket = aws.s3.Bucket("web")
        aws.s3.BucketPublicAccessBlock(
            "web-public-block",
            bucket=self.bucket.id,
            block_public_acls=True,
            block_public_policy=True,
            ignore_public_acls=True,
            restrict_public_buckets=True,
        )
        oac = aws.cloudfront.OriginAccessControl(
            "web-oac",
            origin_access_control_origin_type="s3",
            signing_behavior="always",
            signing_protocol="sigv4",
        )
        spa = aws.cloudfront.Function(
            "spa-rewrite", runtime="cloudfront-js-2.0", code=SPA_REWRITE, publish=True
        )
        security_headers = aws.cloudfront.ResponseHeadersPolicy(
            "web-security-headers",
            name=f"soft-floyd-{pulumi.get_stack()}-security",
            security_headers_config={
                "content_security_policy": {"content_security_policy": UI_CSP, "override": True},
                "content_type_options": {"override": True},
                "frame_options": {"frame_option": "DENY", "override": True},
                "referrer_policy": {"referrer_policy": "no-referrer", "override": True},
                "strict_transport_security": {
                    "access_control_max_age_sec": 31536000,
                    "override": True,
                },
            },
        )

        backend_behavior = {
            "target_origin_id": "api",
            "viewer_protocol_policy": "https-only",
            "allowed_methods": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
            "cached_methods": ["GET", "HEAD"],
            "cache_policy_id": CACHING_DISABLED,
            "origin_request_policy_id": ALL_VIEWER_EXCEPT_HOST,
            "response_headers_policy_id": security_headers.id,
            # Compression would buffer the SSE coach stream.
            "compress": False,
        }

        self.distribution = aws.cloudfront.Distribution(
            "web",
            enabled=True,
            is_ipv6_enabled=True,
            http_version="http2and3",
            price_class="PriceClass_100",
            default_root_object="index.html",
            origins=[
                {
                    "origin_id": "web",
                    "domain_name": self.bucket.bucket_regional_domain_name,
                    "origin_access_control_id": oac.id,
                },
                {
                    "origin_id": "api",
                    "domain_name": origin_domain,
                    "custom_origin_config": {
                        "http_port": 8000,
                        "https_port": 443,
                        "origin_protocol_policy": "http-only",
                        "origin_ssl_protocols": ["TLSv1.2"],
                        "origin_read_timeout": 60,
                        "origin_keepalive_timeout": 5,
                    },
                    "custom_headers": [{"name": "X-Origin-Verify", "value": origin_verify_secret}],
                },
            ],
            default_cache_behavior={
                "target_origin_id": "web",
                "viewer_protocol_policy": "redirect-to-https",
                "allowed_methods": ["GET", "HEAD", "OPTIONS"],
                "cached_methods": ["GET", "HEAD"],
                "cache_policy_id": CACHING_OPTIMIZED,
                "response_headers_policy_id": security_headers.id,
                "compress": True,
                "function_associations": [
                    {"event_type": "viewer-request", "function_arn": spa.arn}
                ],
            },
            ordered_cache_behaviors=[
                {**backend_behavior, "path_pattern": "/api/*"},
                {**backend_behavior, "path_pattern": "/mcp*"},
            ],
            restrictions={"geo_restriction": {"restriction_type": "none"}},
            viewer_certificate={"cloudfront_default_certificate": True},
        )

        aws.s3.BucketPolicy(
            "web-policy",
            bucket=self.bucket.id,
            policy=pulumi.Output.all(self.bucket.arn, self.distribution.arn).apply(
                lambda a: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "cloudfront.amazonaws.com"},
                                "Action": "s3:GetObject",
                                "Resource": f"{a[0]}/*",
                                "Condition": {"StringEquals": {"AWS:SourceArn": a[1]}},
                            }
                        ],
                    }
                )
            ),
        )

    @property
    def domain(self) -> pulumi.Output[str]:
        return self.distribution.domain_name
