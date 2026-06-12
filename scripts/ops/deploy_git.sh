#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
require_confirm_prod "${env}" "$@"

target="${TD_GIT_REF:-}"
for i in "$@"; do
  if [[ "$i" == "--ref="* ]]; then
    target="${i#--ref=}"
  fi
done

if [[ -z "${target}" ]]; then
  die "Missing --ref=<git-ref> (or TD_GIT_REF). Examples: --ref=origin/main, --ref=ce96a68"
fi

cd "${ROOT_DIR}"

if [[ -n "$(git status --porcelain=v1)" ]]; then
  die "Working tree is dirty; commit/stash before deploy_git"
fi

audit_log "deploy_git" "${env}" "$@"

echo "Fetching..."
git fetch --all --prune

echo "Checking out ${target}..."
git checkout --detach "${target}"

echo "Deploying ${env} at $(git rev-parse --short HEAD)..."
"${ROOT_DIR}/scripts/ops/deploy.sh" --env "${env}" --yes

echo "deploy_git complete."

