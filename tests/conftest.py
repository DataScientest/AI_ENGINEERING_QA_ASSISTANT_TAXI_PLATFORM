"""Shared fixtures of the TaxiFare test suite."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from services.prediction_api import app as api

VALID_REQUEST = dict(vendor_id=1, passenger_count=1, rate_code_id=1, pu_location_id=48, do_location_id=79,
                     pickup_hour=14, pickup_dayofweek=2, pickup_month=1, pickup_weekday=1)


class DummyModel:
    """Stands in for the champion model: always predicts 12.5."""

    def predict(self, frame):
        return np.array([12.5])


@pytest.fixture
def valid_request():
    return dict(VALID_REQUEST)


@pytest.fixture
def client(monkeypatch):
    """API client with a dummy champion (version 7) loaded."""
    monkeypatch.setattr(api, "model", DummyModel())
    monkeypatch.setattr(api, "current_model_version", "7")
    return TestClient(api.app)


@pytest.fixture
def raw_trips():
    """Factory of raw TLC-like trips, as downloaded (source column names). 2024-01-01 is a Monday."""

    def _make(n=200, freq="min"):
        return pd.DataFrame({
            "VendorID": np.ones(n), "RatecodeID": np.ones(n),
            "PULocationID": np.arange(n) % 200 + 1, "DOLocationID": np.arange(n) % 150 + 1,
            "passenger_count": np.ones(n),
            "tpep_pickup_datetime": pd.date_range("2024-01-01", periods=n, freq=freq),
            "fare_amount": np.arange(n) % 50 + 5.0,
        })

    return _make
