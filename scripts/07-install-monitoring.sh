#!/usr/bin/env bash
set -euo pipefail

MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"
MONITORING_DIR="${MONITORING_DIR:-k8s/monitoring}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command '$1' not found in PATH" >&2
    exit 1
  }
}

require_cmd kubectl
require_cmd helm

echo "Creating monitoring namespace"
kubectl apply -f "$MONITORING_DIR/namespace.yaml"

echo "Exposing ingress-nginx metrics for api-gateway monitoring"
kubectl -n ingress-nginx patch service ingress-nginx-controller --type merge -p '{"metadata":{"annotations":{"prometheus.io/scrape":"true","prometheus.io/path":"/metrics","prometheus.io/port":"10254"}},"spec":{"ports":[{"name":"http","port":80,"protocol":"TCP","targetPort":"http","appProtocol":"http"},{"name":"https","port":443,"protocol":"TCP","targetPort":"https","appProtocol":"https"},{"name":"metrics","port":10254,"protocol":"TCP","targetPort":10254}]}}'

echo "Applying Grafana dashboard config"
kubectl apply -f "$MONITORING_DIR/grafana-dashboard-configmap.yaml"

echo "Adding Helm repos"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null

echo "Installing Prometheus"
helm upgrade --install monitoring prometheus-community/prometheus \
  --namespace "$MONITORING_NAMESPACE" \
  --create-namespace \
  -f "$MONITORING_DIR/prometheus-values.yaml" \
  --wait

echo "Installing Grafana"
helm upgrade --install grafana grafana/grafana \
  --namespace "$MONITORING_NAMESPACE" \
  --create-namespace \
  -f "$MONITORING_DIR/grafana-values.yaml" \
  --wait

echo "Monitoring pods"
kubectl get pods -n "$MONITORING_NAMESPACE"

echo
echo "Prometheus: kubectl -n $MONITORING_NAMESPACE port-forward svc/monitoring-prometheus-server 9090:80"
echo "Grafana:    kubectl -n $MONITORING_NAMESPACE port-forward svc/grafana 3000:80"
echo "Grafana login: admin / admin"
