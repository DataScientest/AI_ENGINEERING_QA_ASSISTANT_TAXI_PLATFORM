import json
import logging

import numpy as np
import pytest
from fastapi.testclient import TestClient

from services.prediction_api import app as api

VALID = dict(vendor_id=1, passenger_count=1, rate_code_id=1, pu_location_id=48, do_location_id=79,
             pickup_hour=14, pickup_dayofweek=2, pickup_month=1, pickup_weekday=1)


class DummyModel:
    def predict(self, frame):
        return np.array([12.5])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "model", DummyModel())
    monkeypatch.setitem(api.state, "model_version", "7")
    return TestClient(api.app)


def test_health_is_503_without_model_and_200_with_one(monkeypatch):
    monkeypatch.setattr(api, "model", None)
    assert TestClient(api.app).get("/health").status_code == 503
    monkeypatch.setattr(api, "model", DummyModel())
    body = TestClient(api.app).get("/health").json()
    assert body["status"] == "ok" and body["smoke_fare"] == 12.5


@pytest.mark.parametrize("field,value", [("pu_location_id", 9999), ("pickup_hour", 99),
                                          ("passenger_count", -1), ("vendor_id", "abc")])
def test_invalid_input_is_rejected_with_422(client, field, value):
    response = client.post("/fare_predict", json={**VALID, field: value})
    assert response.status_code == 422
    assert field in response.json()["fields"]


def test_valid_request_returns_prediction_and_request_id(client):
    response = client.post("/fare_predict", json=VALID, headers={"X-Request-ID": "abc-123"})
    assert response.json() == {"predicted_fare": 12.5}
    assert response.headers["x-request-id"] == "abc-123"
