# Monitoring Setup

Monitoring is intentionally simple:

- `Prometheus` scrapes the platform metrics
- `Grafana` shows one ready-made dashboard
- `kube-state-metrics` provides pod restart data
- `Alertmanager` is installed with Prometheus so alert rules load cleanly

All monitoring components run in a separate `monitoring` namespace.

## Monitoring Scope

The four required services are monitored as follows:

- `api-gateway`: scraped from the `ingress-nginx` controller metrics endpoint
- `auth-service`: scraped from `/metrics`
- `triage-engine`: scraped from `/metrics`
- `mock-ai-service`: scraped from `/metrics`

Grafana includes:

- request rate
- p95 latency
- error rate
- pod restarts in the last 10 minutes

## Install

Deploy the app first, then install monitoring:

```bash
make create-cluster
make build
make load
make deploy
make monitoring
```

Open the UIs:

```bash
kubectl -n monitoring port-forward svc/monitoring-prometheus-server 9090:80
kubectl -n monitoring port-forward svc/grafana 3000:80
```

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`
- Grafana login: `admin / admin`

Grafana credentials are intentionally simple for this local assignment cluster.

## Configured Alerts

- `CRITICAL`: `triage-engine` down for more than 30 seconds
- `CRITICAL`: `mock-ai-service` p95 latency above 3 seconds for 2 minutes
- `WARNING`: error rate above 5% for 5 minutes on `api-gateway`, `auth-service`, `triage-engine`, or `mock-ai-service`
- `WARNING`: any pod restarts more than 3 times in 10 minutes

## Demo Notes

### 1. Trigger `triage-engine down`

```bash
kubectl -n healthcare-triage-dev scale deployment/triage-engine --replicas=0
```

Wait about 30 seconds, then check **Prometheus -> Alerts** or Grafana.

Restore it:

```bash
kubectl -n healthcare-triage-dev scale deployment/triage-engine --replicas=2
kubectl -n healthcare-triage-dev rollout status deployment/triage-engine
```

### 2. `mock-ai-service` high latency alert note

`mock-ai-service` delay is hard-coded to `500-2000ms`, so the
`p95 > 3s` alert is configured but does not normally fire in the default setup.

To generate equivalent end-to-end traffic, run the verify script:

```bash
./scripts/05-verify.sh
```

This script includes ingress fallback logic, so manual ingress port-forward is
usually not needed.

If you still need manual forwarding, use:

```bash
kubectl -n ingress-nginx port-forward service/ingress-nginx-controller 8080:80
```
