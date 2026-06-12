#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-healthcare-triage}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command '$1' not found in PATH" >&2
    exit 1
  }
}

require_cmd kind

echo "Loading images into Kind cluster: $CLUSTER_NAME"
kind load docker-image auth-service:latest --name "$CLUSTER_NAME"
kind load docker-image triage-engine:latest --name "$CLUSTER_NAME"
kind load docker-image mock-ai-service:latest --name "$CLUSTER_NAME"

echo "Image load complete"
