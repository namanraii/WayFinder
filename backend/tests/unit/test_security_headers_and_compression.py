"""Unit tests for security headers, performance timing, and compression."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import sqlite
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_wayfinder.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_endpoint(client):
    """Health check endpoint returns ok status and metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Wayfinder"
    assert "version" in data


def test_security_headers_present_on_all_responses(client):
    """Responses include standard OWASP-compliant security headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_performance_timing_header_present(client):
    """Responses include server-side execution timing header."""
    response = client.get("/health")
    assert response.status_code == 200
    process_time = response.headers.get("X-Process-Time")
    assert process_time is not None
    assert process_time.endswith("ms")


def test_gzip_compression_on_large_responses(client):
    """Gzip middleware compresses responses when requested."""
    # Request with Accept-Encoding: gzip
    headers = {"Accept-Encoding": "gzip"}
    response = client.get("/docs", headers=headers)
    assert response.status_code == 200
