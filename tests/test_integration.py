"""End-to-end tests: they need the platform running (`make up`) with a champion model."""
import os

import pytest
import requests

API = os.getenv("API_URL", "http://localhost:8000")


def platform_up():
    try:
        return requests.get(f"{API}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not platform_up(), reason="platform not running (make up) or no champion yet")]


def test_health_reports_a_loaded_champion():
    body = requests.get(f"{API}/health", timeout=5).json()
    assert body["status"] == "ok" and body["model_loaded"] is True


def test_a_trip_gets_a_positive_fare():
    response = requests.post(f"{API}/fare_predict", json={"pu_location_id": 132, "do_location_id": 230}, timeout=10)
    assert response.status_code == 200 and response.json()["predicted_fare"] > 0
