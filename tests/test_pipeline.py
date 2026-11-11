from services.pipeline.flow import FEATURES, prepare


def test_preparation_returns_the_features_and_the_target(raw_trips):
    df = prepare(raw_trips())
    assert list(df.columns) == FEATURES + ["total_fare"]
    assert len(df) == 200
