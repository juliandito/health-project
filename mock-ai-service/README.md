# Mock AI Triage Service

Echo service that simulates an LLM-powered medical triage engine.
**For DevOps assessment use only — not real medical AI.**

## What It Does

- Accepts symptom descriptions via `POST /api/v1/triage`
- Echoes back the input wrapped in a diagnosis-like JSON structure
- Adds random processing delay (500ms–2s) to simulate real inference latency
- Returns 500 errors ~10% of the time for circuit breaker testing
- Exposes Prometheus metrics at `/metrics`

## Quick Start

```bash
# Local
pip install -r requirements.txt
python main.py

# Docker
docker build -t mock-ai-triage:latest .
docker run -p 8000:8000 mock-ai-triage:latest
```

## Test Request

```bash
curl -X POST http://localhost:8000/api/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"symptoms": "headache and fever for 3 days"}'
```

## Example Response

```json
{
  "request_id": "a1b2c3d4-...",
  "timestamp": "2026-04-01T10:00:00Z",
  "model": "mock-ai-triage-v1.0",
  "processing_time_ms": 1247.3,
  "input_echo": {
    "symptoms": "headache and fever for 3 days",
    "tokens_received": 7
  },
  "triage_result": {
    "urgency_level": "medium",
    "care_pathway": "SCHEDULE_PRIMARY_CARE",
    "confidence_score": 0.85,
    "recommendation": "Based on reported symptoms: 'headache and fever for 3 days'. Urgency classified as MEDIUM. Recommended pathway: SCHEDULE_PRIMARY_CARE.",
    "disclaimer": "THIS IS A MOCK SERVICE — NOT REAL MEDICAL ADVICE"
  }
}
```

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/triage` | POST | Submit symptoms, get mock triage result |
| `/health` | GET | Liveness probe (K8s) |
| `/ready` | GET | Readiness probe (K8s) |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/info` | GET | Service info and config |

## Configuration

Modify these constants in `main.py`:

| Variable | Default | Description |
|---|---|---|
| `MIN_DELAY_MS` | 500 | Minimum simulated processing delay |
| `MAX_DELAY_MS` | 2000 | Maximum simulated processing delay |
| `ERROR_RATE` | 0.10 | Probability of returning a 500 error |
