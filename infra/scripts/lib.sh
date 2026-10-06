#!/bin/bash
# Shared helpers. Source this; do not run it.
# Reads stack outputs from the current Pulumi stack (run `pulumi login` and
# `pulumi stack select prod` first).

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_DIR/.." && pwd)"

out() {
  (cd "$INFRA_DIR" && pulumi stack output "$1")
}

# run_remote "<shell script>" — runs on the instance through SSM and prints its output.
run_remote() {
  local instance_id region params command_id
  instance_id="$(out instance_id)"
  region="$(out region)"
  params="$(mktemp)"
  python3 -c 'import json,sys; print(json.dumps({"commands":[sys.argv[1]]}))' "$1" > "$params"
  command_id="$(aws ssm send-command --region "$region" --instance-ids "$instance_id" \
    --document-name AWS-RunShellScript --parameters "file://$params" \
    --query Command.CommandId --output text)"
  rm -f "$params"
  aws ssm wait command-executed --region "$region" --command-id "$command_id" \
    --instance-id "$instance_id" || true
  aws ssm get-command-invocation --region "$region" --command-id "$command_id" \
    --instance-id "$instance_id" --query '[Status,StandardOutputContent,StandardErrorContent]' \
    --output text
}
