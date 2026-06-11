# System Architecture

## Service Flow

```
                         ┌──────────────────────────────────────────────┐
                         │            Kubernetes Cluster                │
                         │                                              │
  Patient ──────────►    │  ┌──────────────┐                            │
  (Mobile/Web)           │  │  API Gateway  │                            │
                         │  │  (Ingress)    │                            │
                         │  └──────┬───────┘                            │
                         │         │                                     │
                         │         ├──────────────────┐                  │
                         │         ▼                  ▼                  │
                         │  ┌──────────────┐   ┌──────────────┐         │
                         │  │ auth-service  │   │triage-engine │         │
                         │  │  :8001        │◄──│  :8002        │         │
                         │  │              │   │              │         │
                         │  │ Verify       │   │ Validate     │         │
                         │  │ membership   │   │ token, call  │         │
                         │  │ Issue token  │   │ AI service   │         │
                         │  └──────────────┘   └──────┬───────┘         │
                         │                            │                  │
                         │                            ▼                  │
                         │                     ┌──────────────┐         │
                         │                     │mock-ai-service│         │
                         │                     │  :8000        │         │
                         │                     │              │         │
                         │                     │ Echo + delay │         │
                         │                     │ ~10% errors  │         │
                         │                     └──────────────┘         │
                         │                                              │
                         └──────────────────────────────────────────────┘
```

## Service Dependencies

```
api-gateway  ──►  auth-service       (authentication requests)
api-gateway  ──►  triage-engine      (triage requests)
triage-engine ──►  auth-service      (token validation)
triage-engine ──►  mock-ai-service   (AI inference)
```

## Network Policy Requirement

```
mock-ai-service:
  ingress:  ALLOW from triage-engine ONLY
  egress:   ALLOW DNS only, DENY all external
```

## Ports

| Service | Container Port | Protocol |
|---------|---------------|----------|
| api-gateway | 80 / 443 | HTTP/HTTPS |
| auth-service | 8001 | HTTP |
| triage-engine | 8002 | HTTP |
| mock-ai-service | 8000 | HTTP |

## All Services Expose

| Endpoint | Purpose |
|----------|---------|
| GET /health | Liveness probe |
| GET /ready | Readiness probe |
| GET /metrics | Prometheus-compatible metrics |
