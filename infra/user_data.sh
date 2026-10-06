#!/bin/bash
# First-boot setup for the Soft Floyd box (Amazon Linux 2023, arm64).
# Placeholders are filled by soft_floyd_infra/backend.py.
set -euxo pipefail

IMAGE="__IMAGE__"
REGISTRY="__REGISTRY__"
BACKUP_BUCKET="__BACKUP_BUCKET__"
PARAM_PREFIX="__PREFIX__"

# 512MB of RAM is too little for dnf itself: swap must exist before any install.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=1024
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a

dnf install -y docker sqlite
systemctl enable --now docker

# Data volume: attached by Pulumi shortly after boot, shows up as nvme1n1.
for _ in $(seq 1 60); do
  [ -b /dev/nvme1n1 ] && break
  sleep 5
done
if ! blkid /dev/nvme1n1 >/dev/null 2>&1; then
  mkfs.ext4 -L softfloyd-data /dev/nvme1n1
fi
mkdir -p /data
grep -q softfloyd-data /etc/fstab || echo 'LABEL=softfloyd-data /data ext4 defaults,nofail 0 2' >> /etc/fstab
mount -a
chown 1000:1000 /data

TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

cat > /usr/local/bin/soft-floyd-prestart <<EOS
#!/bin/bash
# Rebuild the env file from SSM and pull the latest image on every (re)start.
set -euo pipefail
export AWS_DEFAULT_REGION=$REGION
aws ssm get-parameters-by-path --path $PARAM_PREFIX --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text \
  | awk -F'\t' '{n=\$1; sub(".*/","",n); print "SOFT_FLOYD_" toupper(n) "=" \$2}' \
  > /etc/soft-floyd.env
chmod 600 /etc/soft-floyd.env
mkdir -p /data
chown 1000:1000 /data
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
docker pull $IMAGE
docker rm -f soft-floyd 2>/dev/null || true
EOS
chmod +x /usr/local/bin/soft-floyd-prestart

cat > /etc/systemd/system/soft-floyd.service <<EOS
[Unit]
Description=Soft Floyd server
After=docker.service network-online.target
Requires=docker.service

[Service]
ExecStartPre=/usr/local/bin/soft-floyd-prestart
ExecStart=/usr/bin/docker run --rm --name soft-floyd --env-file /etc/soft-floyd.env -v /data:/data -p 8000:8000 $IMAGE
ExecStop=/usr/bin/docker stop soft-floyd
# The image does not exist until the first deploy-backend run: keep retrying.
Restart=always
RestartSec=30
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOS

cat > /usr/local/bin/soft-floyd-backup <<EOS
#!/bin/bash
# Consistent SQLite snapshot plus Garmin tokens and FIT files -> S3 (30-day retention).
set -euo pipefail
export AWS_DEFAULT_REGION=$REGION
day=\$(date +%F)
work=\$(mktemp -d)
trap 'rm -rf "\$work"' EXIT
sqlite3 /data/soft-floyd-accounts.db ".backup '\$work/soft-floyd-accounts.db'"
gzip "\$work/soft-floyd-accounts.db"
aws s3 cp "\$work/soft-floyd-accounts.db.gz" "s3://$BACKUP_BUCKET/db/\$day.db.gz"
tar -C /data -czf "\$work/files.tar.gz" --ignore-failed-read fit garmin
aws s3 cp "\$work/files.tar.gz" "s3://$BACKUP_BUCKET/files/\$day.tar.gz"
EOS
chmod +x /usr/local/bin/soft-floyd-backup

cat > /etc/systemd/system/soft-floyd-backup.service <<EOS
[Unit]
Description=Soft Floyd backup to S3

[Service]
Type=oneshot
ExecStart=/usr/local/bin/soft-floyd-backup
EOS

cat > /etc/systemd/system/soft-floyd-backup.timer <<EOS
[Unit]
Description=Nightly Soft Floyd backup

[Timer]
OnCalendar=*-*-* 08:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOS

systemctl daemon-reload
systemctl enable --now soft-floyd.service soft-floyd-backup.timer
