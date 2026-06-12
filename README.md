# Healthcare AI Triage Platform — DevOps Assessment

## Overview

You are the first DevOps engineer for a healthcare AI triage platform. The application code exists but **nothing is containerized, deployed, or monitored**. Build the infrastructure from scratch.

## Repository Structure

```
├── auth-service/           # Membership verification & token issuance
│   ├── main.py             # FastAPI application
│   ├── requirements.txt    # Python dependencies
│   └── test_main.py        # Unit tests (pytest)
├── triage-engine/          # Core triage orchestrator
│   ├── main.py             # FastAPI application (calls auth + AI service)
│   ├── requirements.txt
│   └── test_main.py
├── mock-ai-service/        # Simulates AI inference engine
│   ├── main.py             # FastAPI echo service with delay + random failures
│   ├── requirements.txt
│   └── README.md           # Detailed API docs
├── ARCHITECTURE.md         # System architecture reference
└── README.md               # This file
```

## Services

| Service | Default Port | Description |
|---------|-------------|-------------|
| **api-gateway** | 80/443 | You set this up (Nginx Ingress or Traefik) |
| **auth-service** | 8001 | Verifies membership, issues session tokens |
| **triage-engine** | 8002 | Accepts symptoms, orchestrates triage flow |
| **mock-ai-service** | 8000 | Simulates AI triage with 500ms–2s delay, ~10% failure rate |

## End-to-End Request Flow

```
Step 1 — Authenticate:
  POST /api/v1/auth/verify
  Body: {"member_id": "MBR001234"}
  Returns: {"session_token": "abc123...", "status": "VERIFIED"}

Step 2 — Submit Triage:
  POST /api/v1/triage
  Header: Authorization: Bearer <session_token>
  Body: {"symptoms": "headache and fever for 3 days"}

  Internal flow:
    triage-engine → auth-service (validate token)
    triage-engine → mock-ai-service (get AI triage result)

  Returns: triage result with care pathway
    - SELF_CARE_ADVISORY (low urgency)
    - SCHEDULE_PRIMARY_CARE (medium urgency)
    - ESCALATE_HOSPITAL (high urgency)
```

## Quick Local Test

```bash
# Terminal 1
cd auth-service && pip install -r requirements.txt && python main.py

# Terminal 2
cd mock-ai-service && pip install -r requirements.txt && python main.py

# Terminal 3
cd triage-engine && pip install -r requirements.txt && python main.py

# Terminal 4 — test the flow
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"member_id": "MBR001234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session_token'])")

curl -X POST http://localhost:8002/api/v1/triage \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"symptoms": "headache and fever for 3 days"}'
```

## Running Tests

```bash
cd auth-service && pip install pytest httpx && pytest test_main.py -v
cd triage-engine && pip install pytest httpx && pytest test_main.py -v
```

## Environment Variables

### triage-engine
| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_SERVICE_URL` | `http://auth-service:8001` | Auth service base URL |
| `AI_SERVICE_URL` | `http://mock-ai-service:8000` | AI service base URL |
| `AI_TIMEOUT_SECONDS` | `10` | Timeout for AI service calls |
| `AI_MAX_RETRIES` | `2` | Max retries on AI failure |

### auth-service
| Variable | Default | Description |
|----------|---------|-------------|
| `TOKEN_EXPIRY_MINUTES` | `60` | Session token TTL |

## Mock AI Service Behavior

- Accepts POST /api/v1/triage with `{"symptoms": "..."}`
- Echoes input wrapped in a diagnosis-like JSON
- Random 500ms–2000ms processing delay
- ~10% of requests return HTTP 500 (test your error handling!)
- Exposes Prometheus metrics at /metrics

## What You Need To Deliver

Refer to the assessment document for details. Summary:

1. **Dockerfiles** for all 3 services (multi-stage, non-root, < 150MB)
2. **Kubernetes manifests** (Deployments, Services, ConfigMaps, Secrets, NetworkPolicy, Ingress)
3. **Working deployment** on any free K8s environment
4. **CI/CD pipeline** (lint → test → build → scan → deploy staging → deploy prod)
5. **Monitoring** (Prometheus + Grafana with dashboard and alerts)
6. **Patch deployment strategy** — demonstrate canary OR blue-green, plus hotfix + rollback
7. **Proof it works** (end-to-end request, NetworkPolicy enforcement, patch rollout)

## After Completing

Share the following with us:
- Git repository URL (or zip)
- Kubeconfig file or cluster access credentials
- Brief note on which cloud/K8s environment you chose and why

## Kubernetes Assignment Automation

Use the automation below to deploy and verify Task 1B/1C quickly.
Environment: Kind on Docker

### Makefile workflow

```bash
make create-cluster
make build
make load
make deploy
make verify
```

Cleanup:

```bash
make clean
```

### One-shot workflow

```bash
./scripts/setup.sh
```

### Script breakdown

- `scripts/01-create-cluster.sh`: creates Kind cluster and installs ingress-nginx
- `scripts/02-build-images.sh`: builds local Docker images
- `scripts/03-load-images.sh`: loads images into Kind
- `scripts/04-deploy.sh`: applies manifests and sets deployment images to local tags
- `scripts/05-verify.sh`: checks pod readiness, E2E flow, NetworkPolicy block, graceful degradation
- `scripts/06-cleanup.sh`: deletes Kind cluster
