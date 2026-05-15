import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from loguru import logger

CATEGORICAL_FEATURES = ["make", "model", "fuel_type", "transmission", "body_type", "source_platform"]
NUMERICAL_FEATURES = ["year", "mileage_km", "engine_size_cc"]
TARGET = "price_usd"

CURRENT_YEAR = 2026


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["age"] = CURRENT_YEAR - df["year"].fillna(CURRENT_YEAR - 5)
    df["age_squared"] = df["age"] ** 2
    df["log_mileage"] = np.log1p(df["mileage_km"].fillna(df["mileage_km"].median()))
    df["mileage_per_year"] = df["mileage_km"].fillna(0) / df["age"].replace(0, 1)
    df["engine_liters"] = df["engine_size_cc"].fillna(1500) / 1000

    df["is_hybrid"] = df["fuel_type"].str.lower().str.contains("hybrid", na=False).astype(int)
    df["is_diesel"] = df["fuel_type"].str.lower().str.contains("diesel", na=False).astype(int)
    df["is_electric"] = df["fuel_type"].str.lower().str.contains("electric", na=False).astype(int)
    df["is_automatic"] = df["transmission"].str.lower().str.contains("auto|cvt", na=False, regex=True).astype(int)
    df["is_suv"] = df["body_type"].str.lower().str.contains("suv|4x4", na=False, regex=True).astype(int)
    df["is_premium_make"] = df["make"].str.lower().isin(
        ["lexus", "mercedes-benz", "bmw", "audi", "land rover", "infiniti"]
    ).astype(int)

    df["engine_x_age"] = df["engine_liters"] * df["age"]
    df["mileage_x_age"] = df["log_mileage"] * df["age"]

    for cat in CATEGORICAL_FEATURES:
        if cat in df.columns:
            df[cat] = df[cat].fillna("Unknown").str.strip().str.title()

    logger.info(f"Feature engineering complete — {df.shape[1]} columns, {len(df)} rows")
    return df


def encode_categorical_features(df: pd.DataFrame, encoders: dict = None, fit: bool = True) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    if encoders is None:
        encoders = {}

    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            continue
        if fit:
            le = LabelEncoder()
            df[f"{col}_encoded"] = le.fit_transform(df[col].fillna("Unknown").astype(str))
            encoders[col] = le
        else:
            le = encoders.get(col)
            if le:
                known = set(le.classes_)
                df[col] = df[col].apply(lambda x: x if x in known else "Unknown")
                if "Unknown" not in known:
                    le.classes_ = np.append(le.classes_, "Unknown")
                df[f"{col}_encoded"] = le.transform(df[col].fillna("Unknown").astype(str))

    return df, encoders


def get_feature_columns() -> list[str]:
    base_numerical = ["age", "age_squared", "log_mileage", "mileage_per_year", "engine_liters",
                      "engine_x_age", "mileage_x_age"]
    binary = ["is_hybrid", "is_diesel", "is_electric", "is_automatic", "is_suv", "is_premium_make"]
    encoded = [f"{c}_encoded" for c in CATEGORICAL_FEATURES]
    return base_numerical + binary + encoded