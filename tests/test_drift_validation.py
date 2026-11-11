import numpy as np
import pandas as pd
import pytest
import yaml

from services.pipeline import flow, taxi_drift, taxi_validation
from tests.test_pipeline import raw_data

FEATURES = flow.FEATURES


def sample(n=3000, seed=0, shift=0.0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        'vendor_id': rng.choice([1, 2], n), 'rate_code_id': rng.choice([1, 2], n, p=[.9, .1]),
        'pu_location_id': np.clip(rng.normal(130 + shift, 40, n), 1, 265).round(),
        'do_location_id': np.clip(rng.normal(140, 50, n), 1, 265).round(),
        'passenger_count': rng.choice([1, 2, 3], n, p=[.7, .2, .1]),
        'pickup_hour': np.clip(rng.normal(14, 4, n), 0, 23).round(), 'pickup_dayofweek': rng.integers(0, 7, n),
        'pickup_month': np.ones(n), 'pickup_weekday': rng.integers(0, 2, n)})


def test_no_drift_between_two_samples_of_the_same_distribution():
    result = taxi_drift.feature_drift(sample(seed=1), sample(seed=2), FEATURES)
    assert result['drift_detected'] is False
    assert result['drift_share'] == 0.0
    assert all(f['psi'] < 0.1 for f in result['features'].values())


def test_injected_drift_is_detected_on_the_right_feature():
    current = sample(seed=2, shift=70)  # pickup zones move by +70
    result = taxi_drift.feature_drift(sample(seed=1), current, FEATURES)
    assert result['features']['pu_location_id']['drifted'] is True
    assert result['features']['do_location_id']['drifted'] is False
    assert result['features']['pu_location_id']['psi'] > 0.2
