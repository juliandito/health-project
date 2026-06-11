import pytest
from fastapi.testclient import TestClient
from main import app, SESSION_STORE

client = TestClient(app)


class TestHealth:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_ready(self):
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"


class TestVerify:
    def test_valid_member(self):
        r = client.post("/api/v1/auth/verify", json={"member_id": "MBR001234"})
        assert r.status_code == 200
        assert r.json()["status"] == "VERIFIED"
        assert len(r.json()["session_token"]) == 48

    def test_invalid_member(self):
        r = client.post("/api/v1/auth/verify", json={"member_id": "INVALID99"})
        assert r.status_code == 401

    def test_short_id(self):
        r = client.post("/api/v1/auth/verify", json={"member_id": "MBR"})
        assert r.status_code == 401

    def test_missing_id(self):
        r = client.post("/api/v1/auth/verify", json={})
        assert r.status_code == 400

    def test_bad_json(self):
        r = client.post("/api/v1/auth/verify", content="not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 400


class TestValidate:
    def test_valid_token(self):
        r = client.post("/api/v1/auth/verify", json={"member_id": "MBR999888"})
        token = r.json()["session_token"]
        r = client.get("/api/v1/auth/validate",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["member_id"] == "MBR999888"

    def test_invalid_token(self):
        r = client.get("/api/v1/auth/validate",
                       headers={"Authorization": "Bearer fake_token"})
        assert r.status_code == 401

    def test_missing_token(self):
        r = client.get("/api/v1/auth/validate")
        assert r.status_code == 401


class TestMetrics:
    def test_metrics(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "auth_requests_total" in r.text
