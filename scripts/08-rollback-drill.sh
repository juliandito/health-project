#!/usr/bin/env bash
# Task rollback drill:
# 1) deploy a deliberately broken image tag
# 2) confirm Kubernetes detects failure (ImagePullBackOff/ErrImagePull)
# 3) rollback with kubectl rollout undo
# 4) verify service health restored within 2 minutes
set -euo pipefail

NAMESPACE="${NAMESPACE:-healthcare-triage-dev}"
DEPLOYMENT="${DEPLOYMENT:-triage-engine}"
CONTAINER_NAME="${CONTAINER_NAME:-triage-engine}"
SERVICE_NAME="${SERVICE_NAME:-triage-engine}"
BROKEN_IMAGE="${BROKEN_IMAGE:-ghcr.io/juliandito/health-triage/triage-engine:does-not-exist}"
RECOVERY_TIMEOUT_SECONDS="${RECOVERY_TIMEOUT_SECONDS:-120}"
LOCAL_HEALTH_PORT="${LOCAL_HEALTH_PORT:-18082}"

PF_PID=""

cleanup() {
  if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" >/dev/null 2>&1; then
    kill "$PF_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command '$1' not found" >&2
    exit 1
  }
}

require_cmd kubectl
require_cmd curl

echo "=== Rollback Drill Start ==="
echo "Namespace: $NAMESPACE"
echo "Deployment: $DEPLOYMENT"
echo "Broken image tag: $BROKEN_IMAGE"

ORIGINAL_IMAGE="$(kubectl -n "$NAMESPACE" get deployment "$DEPLOYMENT" -o jsonpath="{.spec.template.spec.containers[?(@.name=='$CONTAINER_NAME')].image}")"
if [[ -z "$ORIGINAL_IMAGE" ]]; then
  echo "Error: could not read original image for container '$CONTAINER_NAME'" >&2
  exit 1
fi

echo "Original image: $ORIGINAL_IMAGE"

START_TS="$(date +%s)"

echo "\nStep 1/4: Deploy broken image"
kubectl -n "$NAMESPACE" set image deployment/"$DEPLOYMENT" "$CONTAINER_NAME"="$BROKEN_IMAGE"

echo "\nStep 2/4: Wait for failure signal (ImagePullBackOff/ErrImagePull)"
FAILED="0"
for _ in $(seq 1 24); do
  OUT="$(kubectl -n "$NAMESPACE" get pods -l app=triage-engine -o wide)"
  if echo "$OUT" | grep -E "ImagePullBackOff|ErrImagePull" >/dev/null 2>&1; then
    FAILED="1"
    echo "$OUT"
    break
  fi
  sleep 5
done

if [[ "$FAILED" != "1" ]]; then
  echo "Did not observe ImagePullBackOff/ErrImagePull within 120s. Capturing rollout status for evidence:"
  kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT" --timeout=30s || true
  echo "Restoring original image before exit..."
  kubectl -n "$NAMESPACE" set image deployment/"$DEPLOYMENT" "$CONTAINER_NAME"="$ORIGINAL_IMAGE"
  kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT" --timeout=180s
  exit 1
fi

echo "\nStep 3/4: Rollback deployment"
kubectl -n "$NAMESPACE" rollout undo deployment/"$DEPLOYMENT"
kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT" --timeout="${RECOVERY_TIMEOUT_SECONDS}s"

echo "\nStep 4/4: Verify service health"
kubectl -n "$NAMESPACE" port-forward service/"$SERVICE_NAME" "$LOCAL_HEALTH_PORT":8002 >/tmp/rollback-drill-portforward.log 2>&1 &
PF_PID=$!

for _ in $(seq 1 10); do
  if curl -sS --connect-timeout 2 "http://127.0.0.1:${LOCAL_HEALTH_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

HEALTH_BODY="$(curl -sS --connect-timeout 3 "http://127.0.0.1:${LOCAL_HEALTH_PORT}/health")"
echo "Health response: $HEALTH_BODY"

END_TS="$(date +%s)"
RECOVERY_SECONDS="$((END_TS - START_TS))"

if [[ "$RECOVERY_SECONDS" -le "$RECOVERY_TIMEOUT_SECONDS" ]]; then
  echo "Recovery SLA met: ${RECOVERY_SECONDS}s (target <= ${RECOVERY_TIMEOUT_SECONDS}s)"
else
  echo "Recovery SLA missed: ${RECOVERY_SECONDS}s (target <= ${RECOVERY_TIMEOUT_SECONDS}s)" >&2
  exit 1
fi

echo "\nRollback drill completed successfully."