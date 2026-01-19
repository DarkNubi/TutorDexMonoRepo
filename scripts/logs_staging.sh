#!/bin/bash
cd "$(dirname "$0")/.."
docker compose -p tutordex-staging logs -f "$@"
