# import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestHealth:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "triage-engine"


class TestMetrics:
    def test_metrics(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "triage_requests_total" in r.text


class TestTriage:
    def test_missing_token(self):
        r = client.post("/api/v1/triage", json={"symptoms": "headache"})
        assert r.status_code == 401
        assert r.json()["error"] == "MISSING_TOKEN"

    def test_missing_symptoms(self):
        with patch("main.validate_token", new_callable=AsyncMock) as m:
            m.return_value = {"status": "VALID", "member_id": "MBR001234"}
            r = client.post("/api/v1/triage", json={},
                            headers={"Authorization": "Bearer mock"})
            assert r.status_code == 400
            assert r.json()["error"] == "MISSING_SYMPTOMS"

    def test_empty_symptoms_rejected(self):
        """Empty string symptoms should be rejected as invalid input."""
        with patch("main.validate_token", new_callable=AsyncMock) as m:
            m.return_value = {"status": "VALID", "member_id": "MBR001234"}
            r = client.post("/api/v1/triage", json={"symptoms": ""},
                            headers={"Authorization": "Bearer mock"})
            assert r.status_code == 400
            assert r.json()["error"] == "MISSING_SYMPTOMS"

    def test_whitespace_only_symptoms_rejected(self):
        """Whitespace-only symptoms should be rejected as invalid input."""
        with patch("main.validate_token", new_callable=AsyncMock) as m:
            m.return_value = {"status": "VALID", "member_id": "MBR001234"}
            r = client.post("/api/v1/triage", json={"symptoms": "   \t\n  "},
                            headers={"Authorization": "Bearer mock"})
            assert r.status_code == 400
            assert r.json()["error"] == "MISSING_SYMPTOMS"

    def test_success(self):
        ai_resp = {
            "request_id": "t-123", "model": "mock-ai-triage-v1.0",
            "processing_time_ms": 750,
            "triage_result": {
                "urgency_level": "medium",
                "care_pathway": "SCHEDULE_PRIMARY_CARE",
                "confidence_score": 0.85,
            },
        }
        with patch("main.validate_token", new_callable=AsyncMock) as ma, \
             patch("main.call_ai_service", new_callable=AsyncMock) as mb:
            ma.return_value = {"status": "VALID", "member_id": "MBR001234"}
            mb.return_value = ai_resp
            r = client.post("/api/v1/triage",
                            json={"symptoms": "fever and headache"},
                            headers={"Authorization": "Bearer mock"})
            assert r.status_code == 200
            d = r.json()
            assert d["status"] == "COMPLETED"
            assert d["care_pathway"] == "SCHEDULE_PRIMARY_CARE"
            assert d["ai_available"] is True

    def test_ai_down_returns_degraded(self):
        with patch("main.validate_token", new_callable=AsyncMock) as ma, \
             patch("main.call_ai_service", new_callable=AsyncMock) as mb:
            ma.return_value = {"status": "VALID", "member_id": "MBR001234"}
            mb.return_value = None
            r = client.post("/api/v1/triage",
                            json={"symptoms": "chest pain"},
                            headers={"Authorization": "Bearer mock"})
            assert r.status_code == 503
            assert r.json()["status"] == "DEGRADED"
            assert r.json()["ai_available"] is False


class TestGetTriage:
    def test_not_found(self):
        r = client.get("/api/v1/triage/nonexistent")
        assert r.status_code == 404
