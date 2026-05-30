"""Smoke tests that need no database (validate the app wiring)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from trip_planner.main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"]
    assert body["version"]


def test_root() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["docs"] == "/docs"
