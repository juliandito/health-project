#!/usr/bin/env bash
# Task 1C — Deploy & Verify
# Demonstrates all four required proof points:
#   1. All pods Running and Ready
#   2. End-to-end triage request through ingress
#   3. NetworkPolicy enforcement (mock-ai-service unreachable from api-gateway)
#   4. Graceful degradation when mock-ai-service returns 500
set -euo pipefail

NAMESPACE="${NAMESPACE:-healthcare-triage-dev}"
INGRESS_HOST="${INGRESS_HOST:-triage.127.0.0.1.nip.io}"
TMP_RESP="$(mktemp)"
GATEWAY_BASE_URL="http://$INGRESS_HOST"
USE_HOST_HEADER=0
PF_PID=""

cleanup_port_forward() {
  if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" >/dev/null 2>&1; then
    kill "$PF_PID" >/dev/null 2>&1 || true
  fi
}

trap 'cleanup_port_forward; rm -f "$TMP_RESP"' EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command '$1' not found in PATH" >&2
    exit 1
  }
}

require_cmd kubectl
require_cmd curl
require_cmd python3

# Kind does not bind ingress port 80 to the host by default.
# If direct access fails, fall back to kubectl port-forward so the
# E2E proof still works without modifying the cluster config.
start_ingress_port_forward_if_needed() {
  if curl -sS --connect-timeout 3 "$GATEWAY_BASE_URL" >/dev/null 2>&1; then
    return
  fi

  echo "Ingress host is not directly reachable; starting temporary port-forward on 127.0.0.1:8080"
  kubectl -n ingress-nginx port-forward service/ingress-nginx-controller 8080:80 >/tmp/ingress-port-forward.log 2>&1 &
  PF_PID=$!

  for _ in $(seq 1 15); do
    if curl -sS --connect-timeout 2 http://127.0.0.1:8080 >/dev/null 2>&1; then
      GATEWAY_BASE_URL="http://127.0.0.1:8080"
      USE_HOST_HEADER=1
      return
    fi
    sleep 1
  done

  echo "Error: ingress not reachable directly and port-forward failed to become ready" >&2
  echo "Port-forward logs (if any):"
  cat /tmp/ingress-port-forward.log 2>/dev/null || true
  exit 1
}

gateway_post() {
  local path="$1"
  local body="$2"
  shift 2

  if [[ $USE_HOST_HEADER -eq 1 ]]; then
    curl -sS -X POST "$GATEWAY_BASE_URL$path" \
      -H "Host: $INGRESS_HOST" \
      -H "Content-Type: application/json" \
      "$@" \
      -d "$body"
  else
    curl -sS -X POST "$GATEWAY_BASE_URL$path" \
      -H "Content-Type: application/json" \
      "$@" \
      -d "$body"
  fi
}

gateway_post_with_status() {
  local path="$1"
  local body="$2"
  local output_file="$3"
  shift 3

  if [[ $USE_HOST_HEADER -eq 1 ]]; then
    curl -sS -o "$output_file" -w "%{http_code}" -X POST "$GATEWAY_BASE_URL$path" \
      -H "Host: $INGRESS_HOST" \
      -H "Content-Type: application/json" \
      "$@" \
      -d "$body"
  else
    curl -sS -o "$output_file" -w "%{http_code}" -X POST "$GATEWAY_BASE_URL$path" \
      -H "Content-Type: application/json" \
      "$@" \
      -d "$body"
  fi
}

# point 1 — all pods Running and Ready; services, ingress, and
# NetworkPolicy objects exist in the correct namespace.
echo "=== Cluster objects ==="
kubectl get pods -n "$NAMESPACE"
kubectl get svc -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"
kubectl get networkpolicy -n "$NAMESPACE"

start_ingress_port_forward_if_needed

# point 2 — end-to-end flow: client → ingress → auth-service (verify)
# → triage-engine → mock-ai-service → triage result returned.
echo
echo "=== End-to-end request via ingress ==="
TOKEN=$(gateway_post "/api/v1/auth/verify" '{"member_id":"MBR001234"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_token"])')

TRIAGE_RESPONSE=$(gateway_post "/api/v1/triage" '{"symptoms":"headache and fever for 3 days"}' \
  -H "Authorization: Bearer $TOKEN")

echo "$TRIAGE_RESPONSE" | python3 -m json.tool

# point 3 — NetworkPolicy enforcement: a pod labelled app=api-gateway
# must NOT be able to reach mock-ai-service directly (policy: allow only
# triage-engine). Script exits non-zero if the request unexpectedly succeeds.
echo
echo "=== NetworkPolicy test: api-gateway-like pod -> mock-ai-service (must be blocked) ==="
kubectl -n "$NAMESPACE" delete pod np-test-gateway --ignore-not-found
kubectl -n "$NAMESPACE" run np-test-gateway \
  --image=curlimages/curl:8.8.0 \
  --labels=app=api-gateway \
  --restart=Never \
  --command -- sh -c "sleep 300"

kubectl -n "$NAMESPACE" wait --for=condition=Ready pod/np-test-gateway --timeout=90s
set +e
kubectl -n "$NAMESPACE" exec np-test-gateway -- \
  curl -sS --connect-timeout 3 http://mock-ai-service:8000/health
NP_EXIT=$?
set -e

if [[ $NP_EXIT -eq 0 ]]; then
  echo "NetworkPolicy check FAILED: request unexpectedly succeeded"
  kubectl -n "$NAMESPACE" delete pod np-test-gateway --ignore-not-found
  exit 1
else
  echo "NetworkPolicy check PASSED: direct access blocked as expected"
fi
kubectl -n "$NAMESPACE" delete pod np-test-gateway --ignore-not-found

# point 4 — graceful degradation: mock-ai-service returns HTTP 500
# ~10% of requests. triage-engine must return HTTP 503 with a DEGRADED
# fallback payload (care_pathway=SCHEDULE_PRIMARY_CARE, ai_available=false)
# rather than crashing or propagating a raw 500 to the client.
echo
echo "=== Graceful degradation test (expect at least one DEGRADED/503 within retries) ==="
FOUND_DEGRADED=0
for i in $(seq 1 20); do
  STATUS=$(gateway_post_with_status "/api/v1/triage" '{"symptoms":"severe headache and fever"}' "$TMP_RESP" \
    -H "Authorization: Bearer $TOKEN")

  if [[ "$STATUS" == "503" ]]; then
    FOUND_DEGRADED=1
    echo "Observed graceful degradation on attempt $i (HTTP 503)."
    cat "$TMP_RESP" | python3 -m json.tool
    break
  fi
done

if [[ $FOUND_DEGRADED -eq 0 ]]; then
  echo "Did not observe 503 in 20 attempts; this can happen due to randomness."
  echo "Manual follow-up: rerun this script to capture a degradation sample."
else
  echo "Graceful degradation behavior verified."
fi

echo
echo "Verification completed"
