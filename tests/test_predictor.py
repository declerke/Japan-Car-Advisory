import pytest
import pandas as pd
import numpy as np
from models.feature_engineering import engineer_features, encode_categorical_features, get_feature_columns


# ── Feature engineering ───────────────────────────────────────────────────────

@pytest.fixture
def sample_car_df():
    return pd.DataFrame([
        {
            "make": "Toyota", "model": "Corolla", "year": 2021,
            "mileage_km": 50_000, "engine_size_cc": 1800,
            "fuel_type": "Petrol", "transmission": "Automatic",
            "body_type": "Sedan", "source_platform": "BE FORWARD",
            "price_usd": 9_000,
        },
        {
            "make": "Honda", "model": "Fit", "year": 2019,
            "mileage_km": 80_000, "engine_size_cc": 1300,
            "fuel_type": "Hybrid", "transmission": "CVT",
            "body_type": "Hatchback", "source_platform": "BE FORWARD",
            "price_usd": 6_500,
        },
        {
            "make": "Nissan", "model": "Note", "year": 2020,
            "mileage_km": 35_000, "engine_size_cc": 1200,
            "fuel_type": "Petrol", "transmission": "CVT",
            "body_type": "Hatchback", "source_platform": "BE FORWARD",
            "price_usd": 7_000,
        },
    ])


def test_engineer_features_adds_age(sample_car_df):
    result = engineer_features(sample_car_df)
    assert "age" in result.columns
    assert (result["age"] >= 0).all()


def test_engineer_features_adds_log_mileage(sample_car_df):
    result = engineer_features(sample_car_df)
    assert "log_mileage" in result.columns
    assert (result["log_mileage"] >= 0).all()


def test_engineer_features_adds_engine_liters(sample_car_df):
    result = engineer_features(sample_car_df)
    assert "engine_liters" in result.columns
    toyota_row = result[result["make"] == "Toyota"].iloc[0]
    assert abs(toyota_row["engine_liters"] - 1.8) < 0.01


def test_engineer_features_hybrid_flag(sample_car_df):
    result = engineer_features(sample_car_df)
    honda_row = result[result["model"].str.contains("Fit", case=False)].iloc[0]
    assert honda_row["is_hybrid"] == 1


def test_engineer_features_automatic_flag(sample_car_df):
    result = engineer_features(sample_car_df)
    toyota_row = result[result["make"] == "Toyota"].iloc[0]
    assert toyota_row["is_automatic"] == 1


def test_encode_categorical_features_fit(sample_car_df):
    engineered = engineer_features(sample_car_df)
    encoded, encoders = encode_categorical_features(engineered, fit=True)
    assert "make_encoded" in encoded.columns
    assert "model_encoded" in encoded.columns
    assert "make" in encoders


def test_encode_categorical_features_transform(sample_car_df):
    engineered = engineer_features(sample_car_df)
    encoded, encoders = encode_categorical_features(engineered, fit=True)

    new_row = pd.DataFrame([{
        "make": "Toyota", "model": "Corolla", "year": 2022,
        "mileage_km": 10_000, "engine_size_cc": 1800,
        "fuel_type": "Petrol", "transmission": "Automatic",
        "body_type": "Sedan", "source_platform": "BE FORWARD",
        "price_usd": 11_000,
    }])
    new_engineered = engineer_features(new_row)
    new_encoded, _ = encode_categorical_features(new_engineered, encoders=encoders, fit=False)
    assert "make_encoded" in new_encoded.columns


def test_get_feature_columns_returns_list():
    cols = get_feature_columns()
    assert isinstance(cols, list)
    assert len(cols) > 0
    assert "age" in cols
    assert "log_mileage" in cols
    assert "make_encoded" in cols


def test_unknown_make_handled_gracefully(sample_car_df):
    engineered = engineer_features(sample_car_df)
    _, encoders = encode_categorical_features(engineered, fit=True)

    new_row = pd.DataFrame([{
        "make": "FantasyBrand", "model": "Phantom", "year": 2021,
        "mileage_km": 5_000, "engine_size_cc": 2000,
        "fuel_type": "Petrol", "transmission": "Automatic",
        "body_type": "Sedan", "source_platform": "BE FORWARD",
        "price_usd": 15_000,
    }])
    new_engineered = engineer_features(new_row)
    new_encoded, _ = encode_categorical_features(new_engineered, encoders=encoders, fit=False)
    assert "make_encoded" in new_encoded.columns
