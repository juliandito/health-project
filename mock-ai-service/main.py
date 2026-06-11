"""
Mock AI Triage Service
----------------------
Simulates an LLM-based triage engine for DevOps assessment purposes.
- Echoes back input symptoms wrapped in a diagnosis-like JSON structure
- Adds random processing delay (500ms - 2s) to simulate real inference
- Randomly returns 500 errors (~10% of requests) for circuit breaker testing
- Exposes /health and /ready endpoints for K8s probes
- Exposes Prometheus metrics at /metrics
"""

import json
import random
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Mock AI Triage Service", version="1.0.0")

# ── Prometheus Metrics ────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "mock_ai_requests_total",
    "Total requests to mock AI service",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "mock_ai_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

# ── Configuration ─────────────────────────────────────────────────────
MIN_DELAY_MS = 500
MAX_DELAY_MS = 2000
ERROR_RATE = 0.10  # 10% random failure rate

# ── Triage severity mapping (keyword-based, no real AI) ───────────────
URGENCY_KEYWORDS = {
    "high": ["chest pain", "difficulty breathing", "unconscious", "seizure",
             "severe bleeding", "stroke", "heart attack", "nyeri dada",
             "sesak napas", "tidak sadarkan diri"],
    "medium": ["fever", "headache", "vomiting", "diarrhea", "cough",
               "abdominal pain", "demam", "sakit kepala", "muntah",
               "batuk", "diare"],
    "low": ["cold", "rash", "sore throat", "runny nose", "fatigue",
            "flu", "pilek", "ruam", "sakit tenggorokan", "lelah"],
}

CARE_PATHWAYS = {
    "high": "ESCALATE_HOSPITAL",
    "medium": "SCHEDULE_PRIMARY_CARE",
    "low": "SELF_CARE_ADVISORY",
}


def classify_urgency(symptoms_text: str) -> str:
    """Simple keyword matching — NOT real triage logic."""
    text = symptoms_text.lower()
    for level in ["high", "medium", "low"]:
        for keyword in URGENCY_KEYWORDS[level]:
            if keyword in text:
                return level
    return "medium"  # default


def build_response(symptoms_text: str, request_id: str) -> dict:
    """Build a diagnosis-like JSON response echoing back the input."""
    urgency = classify_urgency(symptoms_text)
    return {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "mock-ai-triage-v1.0",
        "processing_time_ms": 0,  # filled later
        "input_echo": {
            "symptoms": symptoms_text,
            "tokens_received": len(symptoms_text.split()),
        },
        "triage_result": {
            "urgency_level": urgency,
            "care_pathway": CARE_PATHWAYS[urgency],
            "confidence_score": round(random.uniform(0.72, 0.98), 2),
            "recommendation": (
                f"Based on reported symptoms: '{symptoms_text}'. "
                f"Urgency classified as {urgency.upper()}. "
                f"Recommended pathway: {CARE_PATHWAYS[urgency]}."
            ),
            "disclaimer": "THIS IS A MOCK SERVICE — NOT REAL MEDICAL ADVICE",
        },
    }


# ── Health & Readiness ────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Liveness probe — is the process alive?"""
    return {"status": "alive", "service": "mock-ai-triage"}


@app.get("/ready")
async def ready():
    """Readiness probe — is the service ready to accept traffic?"""
    return {"status": "ready", "service": "mock-ai-triage"}


# ── Prometheus Metrics Endpoint ───────────────────────────────────────
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Main Triage Endpoint ──────────────────────────────────────────────
@app.post("/api/v1/triage")
async def triage(request: Request):
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Simulate random failure (~10%)
    if random.random() < ERROR_RATE:
        delay = random.uniform(0.1, 0.5)
        time.sleep(delay)
        elapsed = round((time.time() - start_time) * 1000, 1)
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "500").inc()
        REQUEST_LATENCY.labels("/api/v1/triage").observe(time.time() - start_time)
        return JSONResponse(
            status_code=500,
            content={
                "request_id": request_id,
                "error": "MODEL_INFERENCE_TIMEOUT",
                "message": "Simulated inference failure — use this to test circuit breakers",
                "processing_time_ms": elapsed,
            },
        )

    # Parse input
    try:
        body = await request.json()
        symptoms = body.get("symptoms", "")
        if not symptoms:
            REQUEST_COUNT.labels("POST", "/api/v1/triage", "400").inc()
            return JSONResponse(
                status_code=400,
                content={"error": "MISSING_SYMPTOMS", "message": "Field 'symptoms' is required"},
            )
    except json.JSONDecodeError:
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "400").inc()
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_JSON", "message": "Request body must be valid JSON"},
        )

    # Simulate processing delay (500ms - 2s)
    delay_seconds = random.uniform(MIN_DELAY_MS / 1000, MAX_DELAY_MS / 1000)
    time.sleep(delay_seconds)

    # Build response
    result = build_response(symptoms, request_id)
    elapsed = round((time.time() - start_time) * 1000, 1)
    result["processing_time_ms"] = elapsed

    REQUEST_COUNT.labels("POST", "/api/v1/triage", "200").inc()
    REQUEST_LATENCY.labels("/api/v1/triage").observe(time.time() - start_time)

    return JSONResponse(status_code=200, content=result)


# ── Info Endpoint ─────────────────────────────────────────────────────
@app.get("/api/v1/info")
async def info():
    return {
        "service": "mock-ai-triage",
        "version": "1.0.0",
        "description": "Echo service with simulated delay for DevOps assessment",
        "config": {
            "min_delay_ms": MIN_DELAY_MS,
            "max_delay_ms": MAX_DELAY_MS,
            "error_rate": ERROR_RATE,
        },
        "endpoints": {
            "POST /api/v1/triage": "Submit symptoms, receive mock triage response",
            "GET /health": "Liveness probe",
            "GET /ready": "Readiness probe",
            "GET /metrics": "Prometheus metrics",
            "GET /api/v1/info": "This endpoint",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
