#!/usr/bin/env bash
set -euo pipefail

failed=0
skipped=0

run_one() {
  local name="$1"
  local cmd="$2"
  echo ""
  echo "==> ${name}"
  set +e
  bash -lc "${cmd}"
  code=$?
  set -e
  if [[ $code -eq 0 ]]; then
    echo "PASS: ${name}"
    return 0
  elif [[ $code -eq 2 ]]; then
    echo "SKIP: ${name}"
    skipped=$((skipped+1))
    return 0
  else
    echo "FAIL: ${name}"
    failed=$((failed+1))
    return 0
  fi
}

run_one "backend" "scripts/smoke_test_backend.sh"
run_one "aggregator" "scripts/smoke_test_aggregator.sh"
run_one "observability" "scripts/smoke_test_observability.sh"

echo ""
if [[ $failed -gt 0 ]]; then
  echo "Smoke tests failed: ${failed}"
  exit 1
fi
if [[ $skipped -gt 0 ]]; then
  echo "Smoke tests skipped: ${skipped}"
  exit 2
fi
echo "All smoke tests passed"
exit 0

