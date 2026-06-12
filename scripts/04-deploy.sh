#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-healthcare-triage-dev}"
K8S_DIR="${K8S_DIR:-k8s}"

if [[ ! -f "$K8S_DIR/namespace.yaml" ]]; then
	echo "Error: namespace manifest not found at $K8S_DIR/namespace.yaml" >&2
	exit 1
fi

echo "Applying namespace manifest"
kubectl apply -f "$K8S_DIR/namespace.yaml"

echo "Waiting for namespace '$NAMESPACE' to become Active"
for _ in $(seq 1 30); do
	PHASE="$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
	if [[ "$PHASE" == "Active" ]]; then
		break
	fi
	sleep 1
done

PHASE="$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.status.phase}')"
if [[ "$PHASE" != "Active" ]]; then
	echo "Error: namespace '$NAMESPACE' did not become Active (phase=$PHASE)" >&2
	exit 1
fi

echo "Applying remaining Kubernetes manifests"
kubectl apply -f "$K8S_DIR/configmap.yaml"
kubectl apply -f "$K8S_DIR/secret.yaml"
kubectl apply -f "$K8S_DIR/service-auth.yaml"
kubectl apply -f "$K8S_DIR/service-mock-ai.yaml"
kubectl apply -f "$K8S_DIR/service-triage.yaml"
kubectl apply -f "$K8S_DIR/deployment-auth.yaml"
kubectl apply -f "$K8S_DIR/deployment-mock-ai.yaml"
kubectl apply -f "$K8S_DIR/deployment-triage.yaml"
kubectl apply -f "$K8S_DIR/networkpolicy.yaml"
kubectl apply -f "$K8S_DIR/ingress.yaml"

echo "Pinning deployments to local Kind images"
kubectl -n "$NAMESPACE" set image deployment/auth-service auth-service=auth-service:latest
kubectl -n "$NAMESPACE" set image deployment/triage-engine triage-engine=triage-engine:latest
kubectl -n "$NAMESPACE" set image deployment/mock-ai-service mock-ai-service=mock-ai-service:latest

echo "Waiting for rollouts"
kubectl -n "$NAMESPACE" rollout status deployment/auth-service --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/triage-engine --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/mock-ai-service --timeout=180s

echo "Deployment complete"
