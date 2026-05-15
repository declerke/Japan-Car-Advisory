import os
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from sklearn.model_selection import KFold, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score, mean_absolute_percentage_error
from loguru import logger
from models.price_predictor import MODEL_DIR, prepare_training_data, load_training_data

EVAL_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "evaluation")
os.makedirs(EVAL_DIR, exist_ok=True)

class ModelEvaluator:
    def __init__(self):
        self.model_path = os.path.join(MODEL_DIR, "price_predictor.joblib")
        self.encoder_path = os.path.join(MODEL_DIR, "encoders.joblib")
        self.meta_path = os.path.join(MODEL_DIR, "model_meta.json")
        self.model = None
        self.encoders = None
        self.meta = None
        self._load_resources()

    def _load_resources(self):
        if os.path.exists(self.model_path):
            self.model = joblib.load(self.model_path)
            self.encoders = joblib.load(self.encoder_path)
            with open(self.meta_path) as f:
                self.meta = json.load(f)
        else:
            logger.error("Model resources not found. Please train the model first.")

    def run_full_evaluation(self, df: pd.DataFrame = None):
        if self.model is None:
            return
        
        logger.info("Starting deep model evaluation...")
        data = load_training_data(df)
        X, y, _, feature_cols = prepare_training_data(data)
        
        y_true = np.expm1(y)
        y_pred = np.expm1(self.model.predict(X))
        
        self.plot_residuals(y_true, y_pred)
        self.plot_feature_importance(feature_cols)
        self.plot_prediction_error(y_true, y_pred)
        self.run_cross_validation(X, y)
        
        logger.info(f"Evaluation complete. Artifacts saved to {EVAL_DIR}")

    def plot_residuals(self, y_true, y_pred):
        residuals = y_true - y_pred
        plt.figure(figsize=(10, 6))
        sns.histplot(residuals, kde=True, color='blue')
        plt.title('Residuals Distribution (Actual - Predicted)')
        plt.xlabel('Price Error (USD)')
        plt.savefig(os.path.join(EVAL_DIR, "residuals_dist.png"))
        plt.close()

    def plot_feature_importance(self, feature_cols):
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            indices = np.argsort(importances)[-15:]
            
            plt.figure(figsize=(10, 8))
            plt.title('Top 15 Feature Importances')
            plt.barh(range(len(indices)), importances[indices], align='center')
            plt.yticks(range(len(indices)), [feature_cols[i] for i in indices])
            plt.xlabel('Relative Importance')
            plt.tight_layout()
            plt.savefig(os.path.join(EVAL_DIR, "feature_importance.png"))
            plt.close()

    def plot_prediction_error(self, y_true, y_pred):
        plt.figure(figsize=(8, 8))
        plt.scatter(y_true, y_pred, alpha=0.3, color='green')
        plt.plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()], 'r--', lw=2)
        plt.title('Actual vs Predicted Prices')
        plt.xlabel('Actual Price (USD)')
        plt.ylabel('Predicted Price (USD)')
        plt.savefig(os.path.join(EVAL_DIR, "actual_vs_pred.png"))
        plt.close()

    def run_cross_validation(self, X, y):
        kf = KFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(self.model, X, y, cv=kf, scoring='neg_mean_absolute_error')
        mae_scores = -cv_scores
        
        cv_summary = {
            "cv_mae_mean": round(float(np.expm1(mae_scores.mean())), 2),
            "cv_mae_std": round(float(np.expm1(mae_scores.std())), 2),
            "n_splits": 5
        }
        
        with open(os.path.join(EVAL_DIR, "cv_report.json"), "w") as f:
            json.dump(cv_summary, f, indent=2)
        
        logger.info(f"CV MAE: ${cv_summary['cv_mae_mean']} (+/- ${cv_summary['cv_mae_std']})")

if __name__ == "__main__":
    evaluator = ModelEvaluator()
    evaluator.run_full_evaluation()