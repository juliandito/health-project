"""
Triage Engine
-------------
Core orchestrator for the healthcare AI triage platform.

Endpoints:
  POST /api/v1/triage        — submit symptoms, get triage result
  GET  /api/v1/triage/{id}   — retrieve a past triage result
  GET  /health               — liveness probe
  GET  /ready                — readiness probe (checks downstream deps)
  GET  /metrics              — Prometheus metrics

Depends on:
  - auth-service      (token validation)
  - mock-ai-service   (AI triage inference)
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://mock-ai-service:8000")
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "10"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"triage-engine","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Triage Engine", version="1.0.0")

REQUEST_COUNT = Counter("triage_requests_total", "Total triage requests",
                        ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("triage_request_duration_seconds", "Triage request latency",
                            ["endpoint"], buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0])
AI_CALL_COUNT = Counter("triage_ai_calls_total", "Calls to AI service", ["status"])
AI_CALL_LATENCY = Histogram("triage_ai_call_duration_seconds", "AI service call latency",
                            buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0])
AUTH_CALL_COUNT = Counter("triage_auth_calls_total", "Calls to auth service", ["status"])

TRIAGE_HISTORY: dict[str, dict] = {}

PATHWAY_DETAILS = {
    "SELF_CARE_ADVISORY": {
        "action": "No further medical attention needed",
        "instructions": "Rest, hydrate, and monitor symptoms. Return if symptoms worsen.",
    },
    "SCHEDULE_PRIMARY_CARE": {
        "action": "Visit a primary care clinic",
        "instructions": "Schedule an appointment within 24-48 hours.",
    },
    "ESCALATE_HOSPITAL": {
        "action": "Go to the nearest hospital emergency department",
        "instructions": "Seek immediate medical attention.",
    },
}


@app.get("/health")
async def health():
    return {"status": "alive", "service": "triage-engine"}


@app.get("/ready")
async def ready():
    checks = {"auth_service": False, "ai_service": False}
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{AUTH_SERVICE_URL}/health")
            checks["auth_service"] = r.status_code == 200
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{AI_SERVICE_URL}/health")
            checks["ai_service"] = r.status_code == 200
    except Exception:
        pass

    all_ready = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"status": "ready" if all_ready else "degraded",
                 "service": "triage-engine", "dependencies": checks},
    )


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def validate_token(token: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{AUTH_SERVICE_URL}/api/v1/auth/validate",
                            headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                AUTH_CALL_COUNT.labels("success").inc()
                return r.json()
            AUTH_CALL_COUNT.labels("invalid").inc()
            return None
    except Exception as e:
        AUTH_CALL_COUNT.labels("error").inc()
        logger.error(f"Auth service call failed: {e}")
        return None


async def call_ai_service(symptoms: str, triage_id: str) -> dict | None:
    for attempt in range(1, AI_MAX_RETRIES + 1):
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as c:
                r = await c.post(f"{AI_SERVICE_URL}/api/v1/triage",
                                 json={"symptoms": symptoms})
                elapsed = time.time() - start
                AI_CALL_LATENCY.observe(elapsed)

                if r.status_code == 200:
                    AI_CALL_COUNT.labels("success").inc()
                    logger.info(f"AI responded in {elapsed:.2f}s for {triage_id} (attempt {attempt})")
                    return r.json()
                else:
                    AI_CALL_COUNT.labels(f"error_{r.status_code}").inc()
                    logger.warning(f"AI returned {r.status_code} for {triage_id} (attempt {attempt})")
        except httpx.TimeoutException:
            AI_CALL_COUNT.labels("timeout").inc()
            logger.warning(f"AI timeout for {triage_id} (attempt {attempt})")
        except httpx.ConnectError:
            AI_CALL_COUNT.labels("connection_error").inc()
            logger.error(f"AI connection failed for {triage_id} (attempt {attempt})")
        except Exception as e:
            AI_CALL_COUNT.labels("error").inc()
            logger.error(f"AI unexpected error: {e} (attempt {attempt})")

        if attempt < AI_MAX_RETRIES:
            time.sleep(0.5 * attempt)

    return None


@app.post("/api/v1/triage")
async def submit_triage(request: Request, authorization: str = Header(default="")):
    start = time.time()
    triage_id = str(uuid.uuid4())
    logger.info(f"New triage request: {triage_id}")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "401").inc()
        return JSONResponse(status_code=401, content={
            "error": "MISSING_TOKEN",
            "message": "Authorization header with Bearer token is required.",
        })

    auth_result = await validate_token(token)
    if not auth_result:
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "401").inc()
        return JSONResponse(status_code=401, content={
            "error": "AUTH_FAILED", "message": "Token validation failed.",
        })

    member_id = auth_result.get("member_id", "unknown")

    try:
        body = await request.json()
    except json.JSONDecodeError:
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "400").inc()
        return JSONResponse(status_code=400, content={
            "error": "INVALID_JSON", "message": "Request body must be valid JSON"
        })

    symptoms = body.get("symptoms", "")
    # BUG-FIX-NEEDED: only checks None/missing, accepts whitespace strings like "   " or ""
    # Candidates should add proper validation: symptoms.strip() check

    # 400 if not a string or empty string
    if not isinstance(symptoms, str) or not symptoms.strip():
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "400").inc()
        return JSONResponse(status_code=400, content={
            "error": "MISSING_SYMPTOMS", "message": "Field 'symptoms' is required"
        })

    logger.info(f"Triage {triage_id}: member={member_id}, symptoms_len={len(symptoms)}")

    ai_result = await call_ai_service(symptoms, triage_id)

    if not ai_result:
        REQUEST_COUNT.labels("POST", "/api/v1/triage", "503").inc()
        REQUEST_LATENCY.labels("/api/v1/triage").observe(time.time() - start)
        fallback = {
            "triage_id": triage_id, "status": "DEGRADED", "member_id": member_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "AI triage service temporarily unavailable. Please visit your nearest clinic.",
            "care_pathway": "SCHEDULE_PRIMARY_CARE",
            "pathway_details": PATHWAY_DETAILS["SCHEDULE_PRIMARY_CARE"],
            "ai_available": False,
        }
        TRIAGE_HISTORY[triage_id] = fallback
        return JSONResponse(status_code=503, content=fallback)

    triage_data = ai_result.get("triage_result", {})
    care_pathway = triage_data.get("care_pathway", "SCHEDULE_PRIMARY_CARE")
    pathway_info = PATHWAY_DETAILS.get(care_pathway, PATHWAY_DETAILS["SCHEDULE_PRIMARY_CARE"])

    result = {
        "triage_id": triage_id, "status": "COMPLETED", "member_id": member_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symptoms_submitted": symptoms,
        "ai_assessment": {
            "urgency_level": triage_data.get("urgency_level", "medium"),
            "confidence_score": triage_data.get("confidence_score", 0.0),
            "model_used": ai_result.get("model", "unknown"),
            "processing_time_ms": ai_result.get("processing_time_ms", 0),
        },
        "care_pathway": care_pathway, "pathway_details": pathway_info,
        "ai_available": True,
        "total_processing_time_ms": round((time.time() - start) * 1000, 1),
    }

    TRIAGE_HISTORY[triage_id] = result
    REQUEST_COUNT.labels("POST", "/api/v1/triage", "200").inc()
    REQUEST_LATENCY.labels("/api/v1/triage").observe(time.time() - start)
    logger.info(f"Triage {triage_id}: completed, pathway={care_pathway}")
    return JSONResponse(status_code=200, content=result)


@app.get("/api/v1/triage/{triage_id}")
async def get_triage(triage_id: str):
    result = TRIAGE_HISTORY.get(triage_id)
    if not result:
        return JSONResponse(status_code=404, content={
            "error": "NOT_FOUND", "message": f"Triage ID '{triage_id}' not found"
        })
    return JSONResponse(status_code=200, content=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
