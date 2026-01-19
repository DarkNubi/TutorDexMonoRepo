#!/usr/bin/env bash
set -euo pipefail

# Simple syntax check for core Python entrypoints.
python -m py_compile TutorDexAggregator/*.py TutorDexAggregator/workers/*.py TutorDexBackend/*.py
echo "Python syntax check passed."
