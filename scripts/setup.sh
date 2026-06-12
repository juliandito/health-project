#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/01-create-cluster.sh
./scripts/02-build-images.sh
./scripts/03-load-images.sh
./scripts/04-deploy.sh
./scripts/05-verify.sh
