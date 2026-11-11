from fastapi.testclient import TestClient

from services.prediction_api import app as api


def test_health_is_503_without_model(monkeypatch):
    monkeypatch.setattr(api, "model", None)
    assert TestClient(api.app).get("/health").status_code == 503


def test_invalid_zone_is_rejected_with_422(client, valid_request):
    response = client.post("/fare_predict", json={**valid_request, "pu_location_id": 9999})
    assert response.status_code == 422
    assert "pu_location_id" in response.json()["fields"]


def test_valid_request_returns_a_prediction(client, valid_request):
    response = client.post("/fare_predict", json=valid_request)
    assert response.status_code == 200
    assert response.json()["predicted_fare"] == 12.5
