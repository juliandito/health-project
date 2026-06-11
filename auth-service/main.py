"""
Auth Service
------------
Handles patient membership verification and session token issuance.

Endpoints:
  POST /api/v1/auth/verify   — verify membership ID, return session token
  GET  /api/v1/auth/validate  — validate an existing session token
  GET  /health                — liveness probe
  GET  /ready                 — readiness probe
  GET  /metrics               — Prometheus metrics
"""

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI(title="Auth Service", version="1.0.0")

REQUEST_COUNT = Counter(
    "auth_requests_total", "Total auth requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "auth_request_duration_seconds", "Auth request latency",
    ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

SESSION_STORE: dict[str, dict] = {}

VALID_PREFIX = "MBR"
TOKEN_EXPIRY_MINUTES = int(os.getenv("TOKEN_EXPIRY_MINUTES", "60"))


def is_valid_member(member_id: str) -> bool:
    return member_id.upper().startswith(VALID_PREFIX) and len(member_id) >= 6


def generate_token(member_id: str) -> str:
    raw = f"{member_id}-{time.time()}-{secrets.token_hex(16)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


@app.get("/health")
async def health():
    return {"status": "alive", "service": "auth-service"}


@app.get("/ready")
async def ready():
    return {"status": "ready", "service": "auth-service"}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/auth/verify")
async def verify_membership(request: Request):
    start = time.time()
    try:
        body = await request.json()
    except json.JSONDecodeError:
        REQUEST_COUNT.labels("POST", "/api/v1/auth/verify", "400").inc()
        return JSONResponse(status_code=400, content={
            "error": "INVALID_JSON", "message": "Request body must be valid JSON"
        })

    member_id = body.get("member_id", "")
    if not member_id:
        REQUEST_COUNT.labels("POST", "/api/v1/auth/verify", "400").inc()
        return JSONResponse(status_code=400, content={
            "error": "MISSING_MEMBER_ID", "message": "Field 'member_id' is required"
        })

    if not is_valid_member(member_id):
        REQUEST_COUNT.labels("POST", "/api/v1/auth/verify", "401").inc()
        REQUEST_LATENCY.labels("/api/v1/auth/verify").observe(time.time() - start)
        return JSONResponse(status_code=401, content={
            "error": "INVALID_MEMBERSHIP",
            "message": f"Member ID '{member_id}' is not valid. Must start with '{VALID_PREFIX}' and be at least 6 characters.",
        })

    token = generate_token(member_id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

    SESSION_STORE[token] = {
        "member_id": member_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    REQUEST_COUNT.labels("POST", "/api/v1/auth/verify", "200").inc()
    REQUEST_LATENCY.labels("/api/v1/auth/verify").observe(time.time() - start)

    return JSONResponse(status_code=200, content={
        "status": "VERIFIED",
        "member_id": member_id,
        "session_token": token,
        "expires_at": expires_at.isoformat(),
    })


@app.get("/api/v1/auth/validate")
async def validate_token(authorization: str = Header(default="")):
    start = time.time()
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        REQUEST_COUNT.labels("GET", "/api/v1/auth/validate", "401").inc()
        return JSONResponse(status_code=401, content={
            "error": "MISSING_TOKEN", "message": "Authorization header with Bearer token is required"
        })

    session = SESSION_STORE.get(token)
    if not session:
        REQUEST_COUNT.labels("GET", "/api/v1/auth/validate", "401").inc()
        REQUEST_LATENCY.labels("/api/v1/auth/validate").observe(time.time() - start)
        return JSONResponse(status_code=401, content={
            "error": "INVALID_TOKEN", "message": "Token not found or expired"
        })

    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        del SESSION_STORE[token]
        REQUEST_COUNT.labels("GET", "/api/v1/auth/validate", "401").inc()
        return JSONResponse(status_code=401, content={
            "error": "TOKEN_EXPIRED", "message": "Session token has expired"
        })

    REQUEST_COUNT.labels("GET", "/api/v1/auth/validate", "200").inc()
    REQUEST_LATENCY.labels("/api/v1/auth/validate").observe(time.time() - start)

    return JSONResponse(status_code=200, content={
        "status": "VALID",
        "member_id": session["member_id"],
        "expires_at": session["expires_at"],
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
