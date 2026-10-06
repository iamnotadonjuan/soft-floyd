"""The one small EC2 box that runs the existing server in Docker.

Reachable only from CloudFront (origin-facing prefix list), managed through
SSM (no SSH), with rider data on a separate protected EBS volume so
replacing the instance never deletes it.
"""

import json
from pathlib import Path

import pulumi
import pulumi_aws as aws

from .secrets import PREFIX

USER_DATA = (Path(__file__).parent.parent / "user_data.sh").read_text()


class Backend:
    def __init__(
        self,
        instance_type: str,
        data_volume_gb: int,
        backup_bucket: aws.s3.Bucket,
        parameter_deps: list[pulumi.Resource],
    ) -> None:
        self.repo = aws.ecr.Repository(
            "server",
            image_tag_mutability="MUTABLE",
            force_delete=True,
            image_scanning_configuration={"scan_on_push": True},
        )
        aws.ecr.LifecyclePolicy(
            "server-keep-recent",
            repository=self.repo.name,
            policy=json.dumps(
                {
                    "rules": [
                        {
                            "rulePriority": 1,
                            "description": "Keep the 5 most recent images",
                            "selection": {
                                "tagStatus": "any",
                                "countType": "imageCountMoreThan",
                                "countNumber": 5,
                            },
                            "action": {"type": "expire"},
                        }
                    ]
                }
            ),
        )

        vpc = aws.ec2.get_vpc(default=True)
        subnet_ids = aws.ec2.get_subnets(filters=[{"name": "vpc-id", "values": [vpc.id]}]).ids
        subnet = aws.ec2.get_subnet(id=sorted(subnet_ids)[0])
        cloudfront = aws.ec2.get_managed_prefix_list(
            name="com.amazonaws.global.cloudfront.origin-facing"
        )

        security_group = aws.ec2.SecurityGroup(
            "server",
            description="Soft Floyd origin: CloudFront only, no SSH",
            vpc_id=vpc.id,
            ingress=[
                {
                    "protocol": "tcp",
                    "from_port": 8000,
                    "to_port": 8000,
                    "prefix_list_ids": [cloudfront.id],
                    "description": "CloudFront origin-facing",
                }
            ],
            egress=[{"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
        )

        role = aws.iam.Role(
            "server",
            assume_role_policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ec2.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )
        aws.iam.RolePolicyAttachment(
            "server-ssm",
            role=role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        )
        caller = aws.get_caller_identity()
        region = aws.get_region()
        aws.iam.RolePolicy(
            "server-inline",
            role=role.id,
            policy=pulumi.Output.all(self.repo.arn, backup_bucket.arn).apply(
                lambda a: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "ecr:GetAuthorizationToken",
                                "Resource": "*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "ecr:BatchGetImage",
                                    "ecr:GetDownloadUrlForLayer",
                                    "ecr:BatchCheckLayerAvailability",
                                ],
                                "Resource": a[0],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "ssm:GetParametersByPath",
                                "Resource": [
                                    f"arn:aws:ssm:{region.region}:{caller.account_id}"
                                    f":parameter{PREFIX}",
                                    f"arn:aws:ssm:{region.region}:{caller.account_id}"
                                    f":parameter{PREFIX}/*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                                "Resource": [a[1], f"{a[1]}/*"],
                            },
                        ],
                    }
                )
            ),
        )
        profile = aws.iam.InstanceProfile("server", role=role.name)

        ami = aws.ssm.get_parameter(
            name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
        ).value

        # Stable public IP + DNS name, independent of the instance, so the
        # CloudFront origin can be created before the instance exists.
        self.eip = aws.ec2.Eip("server", domain="vpc")

        self.data_volume = aws.ebs.Volume(
            "data",
            availability_zone=subnet.availability_zone,
            size=data_volume_gb,
            type="gp3",
            encrypted=True,
            opts=pulumi.ResourceOptions(protect=True),
        )

        self.instance_args = {
            "ami": ami,
            "instance_type": instance_type,
            "subnet_id": subnet.id,
            "availability_zone": subnet.availability_zone,
            "vpc_security_group_ids": [security_group.id],
            "iam_instance_profile": profile.name,
            "metadata_options": {"http_tokens": "required", "http_endpoint": "enabled"},
            "root_block_device": {"volume_size": 8, "volume_type": "gp3", "encrypted": True},
        }
        self.backup_bucket = backup_bucket
        self.parameter_deps = parameter_deps

    def create_instance(self) -> aws.ec2.Instance:
        user_data = pulumi.Output.all(self.repo.repository_url, self.backup_bucket.bucket).apply(
            lambda a: (
                USER_DATA.replace("__IMAGE__", f"{a[0]}:latest")
                .replace("__REGISTRY__", a[0].split("/")[0])
                .replace("__BACKUP_BUCKET__", a[1])
                .replace("__PREFIX__", PREFIX)
            )
        )
        instance = aws.ec2.Instance(
            "server",
            user_data=user_data,
            user_data_replace_on_change=True,
            tags={"Name": "soft-floyd"},
            opts=pulumi.ResourceOptions(
                depends_on=self.parameter_deps,
                # A newer AMI must not silently replace the box.
                ignore_changes=["ami"],
                # The data volume can only attach to one instance: the old box
                # (and its attachment) must go before the new one is created.
                delete_before_replace=True,
            ),
            **self.instance_args,
        )
        aws.ec2.EipAssociation("server", instance_id=instance.id, allocation_id=self.eip.id)
        aws.ec2.VolumeAttachment(
            "data",
            device_name="/dev/sdf",
            volume_id=self.data_volume.id,
            instance_id=instance.id,
            stop_instance_before_detaching=True,
        )
        return instance
