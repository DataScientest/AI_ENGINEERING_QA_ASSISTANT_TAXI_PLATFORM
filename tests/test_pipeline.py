import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from services.pipeline.flow import prepare, ingest, FEATURES


def raw_data(n=200):
    return pd.DataFrame({'VendorID': np.ones(n), 'RatecodeID': np.ones(n),
        'PULocationID': np.arange(n) % 200 + 1, 'DOLocationID': np.arange(n) % 150 + 1,
        'passenger_count': np.ones(n), 'tpep_pickup_datetime': pd.date_range('2024-01-01', periods=n, freq='min'),
        'fare_amount': np.arange(n) % 50 + 5.0})


def test_preparation_features():
    df = prepare(raw_data())
    assert list(df.columns) == FEATURES + ['total_fare']
    assert len(df) == 200
    assert (df.total_fare > 0).all()
