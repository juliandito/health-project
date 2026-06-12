#!/usr/bin/env bash
set -euo pipefail

echo "Building service images"
docker build -t auth-service:latest ./auth-service
docker build -t triage-engine:latest ./triage-engine
docker build -t mock-ai-service:latest ./mock-ai-service

echo "Image build complete"
