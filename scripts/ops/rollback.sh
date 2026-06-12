#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
require_confirm_prod "${env}" "$@"

ref="${TD_ROLLBACK_REF:-}"
for i in "$@"; do
  if [[ "$i" == "--to="* ]]; then
    ref="${i#--to=}"
  fi
done

if [[ -z "${ref}" ]]; then
  die "Missing --to=<git-ref> (or TD_ROLLBACK_REF). Uses deploy_git under the hood."
fi

audit_log "rollback" "${env}" "$@"

exec "${ROOT_DIR}/scripts/ops/deploy_git.sh" --env "${env}" --ref="${ref}" --yes

