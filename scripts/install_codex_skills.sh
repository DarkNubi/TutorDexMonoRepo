#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/codex_skills"

CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
DEST_DIR="${CODEX_HOME}/skills"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "ERROR: skills source dir not found: ${SRC_DIR}" >&2
  exit 1
fi

mkdir -p "${DEST_DIR}"

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
fi

copied=0
skipped=0
while IFS= read -r -d '' d; do
  name="$(basename "$d")"
  target="${DEST_DIR}/${name}"
  if [[ -e "${target}" && $force -ne 1 ]]; then
    echo "SKIP: ${name} (exists)"
    skipped=$((skipped+1))
    continue
  fi
  rm -rf "${target}"
  cp -R "${d}" "${target}"
  echo "OK: ${name}"
  copied=$((copied+1))
done < <(find "${SRC_DIR}" -mindepth 1 -maxdepth 1 -type d -print0)

echo "Done. copied=${copied} skipped=${skipped} dest=${DEST_DIR}"

