import os
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from loguru import logger
from models.feature_engineering import engineer_features, encode_categorical_features, get_feature_columns, TARGET

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "models")
os.makedirs(MODEL_DIR, exist_ok=True)


def load_training_data(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if df is not None:
        return df

    from etl.loader import load_japan_listings
    logger.info("Loading training data from database")
    data = load_japan_listings(limit=50000)
    return data


def prepare_training_data(df: pd.DataFrame) -> tuple:
    df = df.dropna(subset=[TARGET, "make", "model", "year", "mileage_km", "engine_size_cc"])
    df = df[df[TARGET].between(500, 150_000)]

    q1 = df[TARGET].quantile(0.01)
    q99 = df[TARGET].quantile(0.99)
    df = df[(df[TARGET] >= q1) & (df[TARGET] <= q99)]

    df = engineer_features(df)
    df, encoders = encode_categorical_features(df, fit=True)

    feature_cols = [c for c in get_feature_columns() if c in df.columns]
    X = df[feature_cols].fillna(0)
    y = np.log1p(df[TARGET])

    logger.info(f"Training data: {len(df)} rows, {len(feature_cols)} features, target range [{df[TARGET].min():.0f}, {df[TARGET].max():.0f}]")
    return X, y, encoders, feature_cols


def build_models() -> dict:
    return {
        "xgboost": XGBRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
        ),
        "lightgbm": LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=50,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=20,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        ),
    }


def evaluate_model(model, X_test: pd.DataFrame, y_test: pd.Series) -> dict:
    y_pred_log = model.predict(X_test)
    y_pred = np.expm1(y_pred_log)
    y_true = np.expm1(y_test)

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    mape = np.mean(np.abs((y_true - y_pred) / y_true.replace(0, np.nan))) * 100

    return {"MAE": round(mae, 2), "RMSE": round(rmse, 2), "R2": round(r2, 4), "MAPE": round(mape, 2)}


def train_and_select_best(df: Optional[pd.DataFrame] = None) -> dict:
    data = load_training_data(df)
    X, y, encoders, feature_cols = prepare_training_data(data)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")

    models = build_models()
    results = {}
    trained_models = {}

    for name, model in models.items():
        logger.info(f"Training {name}...")
        model.fit(X_train, y_train)
        metrics = evaluate_model(model, X_test, y_test)
        results[name] = metrics
        trained_models[name] = model
        logger.info(f"{name} — MAE: ${metrics['MAE']:,.0f} | RMSE: ${metrics['RMSE']:,.0f} | R2: {metrics['R2']:.3f} | MAPE: {metrics['MAPE']:.1f}%")

    best_name = min(results, key=lambda k: results[k]["MAE"])
    best_model = trained_models[best_name]
    logger.info(f"Best model: {best_name} with MAE ${results[best_name]['MAE']:,.0f}")

    model_path = os.path.join(MODEL_DIR, "price_predictor.joblib")
    encoder_path = os.path.join(MODEL_DIR, "encoders.joblib")
    meta_path = os.path.join(MODEL_DIR, "model_meta.json")

    joblib.dump(best_model, model_path)
    joblib.dump(encoders, encoder_path)

    meta = {
        "model_name": best_name,
        "trained_at": datetime.utcnow().isoformat(),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_cols": feature_cols,
        "metrics": results,
        "best_metrics": results[best_name],
        "version": "1.0.0",
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"Model saved to {model_path}")
    return meta


class PricePredictor:
    def __init__(self):
        self.model = None
        self.encoders = None
        self.meta = None
        self.feature_cols = None
        self._load()

    def _load(self):
        model_path = os.path.join(MODEL_DIR, "price_predictor.joblib")
        encoder_path = os.path.join(MODEL_DIR, "encoders.joblib")
        meta_path = os.path.join(MODEL_DIR, "model_meta.json")

        if not os.path.exists(model_path):
            logger.warning("No trained model found. Train the model first using train_and_select_best()")
            return

        self.model = joblib.load(model_path)
        self.encoders = joblib.load(encoder_path)
        with open(meta_path) as f:
            self.meta = json.load(f)
        self.feature_cols = self.meta["feature_cols"]
        logger.info(f"Model loaded: {self.meta['model_name']} (trained {self.meta['trained_at'][:10]})")

    def predict(
        self,
        make: str,
        model: str,
        year: int,
        mileage_km: int,
        engine_size_cc: int,
        fuel_type: str = "Petrol",
        transmission: str = "Automatic",
        body_type: str = "Sedan",
        source_platform: str = "BE FORWARD",
    ) -> dict:
        if self.model is None:
            return {"error": "No model loaded. Run training first."}

        row = pd.DataFrame([{
            "make": make, "model": model, "year": year, "mileage_km": mileage_km,
            "engine_size_cc": engine_size_cc, "fuel_type": fuel_type,
            "transmission": transmission, "body_type": body_type,
            "source_platform": source_platform,
        }])

        row = engineer_features(row)
        row, _ = encode_categorical_features(row, encoders=self.encoders, fit=False)

        available = [c for c in self.feature_cols if c in row.columns]
        missing = [c for c in self.feature_cols if c not in row.columns]
        for col in missing:
            row[col] = 0

        X = row[self.feature_cols].fillna(0)
        log_pred = self.model.predict(X)[0]
        pred_price = float(np.expm1(log_pred))

        uncertainty_factor = 0.15
        lower = pred_price * (1 - uncertainty_factor)
        upper = pred_price * (1 + uncertainty_factor)

        return {
            "predicted_price_usd": round(pred_price, 2),
            "lower_bound_usd": round(lower, 2),
            "upper_bound_usd": round(upper, 2),
            "model_used": self.meta.get("model_name", "unknown"),
            "model_version": self.meta.get("version", "1.0.0"),
            "confidence_note": f"±{uncertainty_factor*100:.0f}% confidence interval",
        }

    def is_ready(self) -> bool:
        return self.model is not None


if __name__ == "__main__":
    meta = train_and_select_best()
    print("Training complete:", json.dumps(meta["best_metrics"], indent=2))