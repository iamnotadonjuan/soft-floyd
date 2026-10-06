"""SSM Parameter Store entries the instance turns into SOFT_FLOYD_* env vars.

The parameter name's last segment, upper-cased, becomes the variable name:
/soft-floyd/openai_api_key -> SOFT_FLOYD_OPENAI_API_KEY.
"""

import pulumi
import pulumi_aws as aws

PREFIX = "/soft-floyd"


def parameters(
    values: dict[str, pulumi.Input[str]], secret_keys: set[str]
) -> list[aws.ssm.Parameter]:
    return [
        aws.ssm.Parameter(
            f"param-{name}",
            name=f"{PREFIX}/{name}",
            type="SecureString" if name in secret_keys else "String",
            value=value,
        )
        for name, value in values.items()
    ]
