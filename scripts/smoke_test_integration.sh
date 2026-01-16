#!/usr/bin/env bash
set -euo pipefail

echo "TutorDex smoke test: integration"
echo "  Running backend smoke test..."
scripts/smoke_test_backend.sh

echo ""
echo "  Running aggregator smoke test..."
scripts/smoke_test_aggregator.sh

