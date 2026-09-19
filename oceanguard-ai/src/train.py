"""Train naive + ML models with chronological splits."""
from __future__ import annotations

from typing import List, Optional, Tuple

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .config_loader import ROOT, load_config
from .data_loader import load_effort
from .features import FEATURE_COLS, build_features
from .preprocessing import save_weekly, to_weekly_grid
from .risk_score import risk_from_prediction, seasonal_baseline


def chronological_split(df: pd.DataFrame, cfg: dict):
    train_end = pd.Timestamp(cfg["splits"]["train_end"])
    valid_end = pd.Timestamp(cfg["splits"]["valid_end"])
    w = pd.to_datetime(df["week_start"])
    train = df[w <= train_end]
    valid = df[(w > train_end) & (w <= valid_end)]
    test = df[w > valid_end]
    # If ranges empty (short demo), fall back to 70/15/15 by time
    if len(train) < 50 or len(test) < 20:
        cuts = w.quantile([0.7, 0.85]).tolist()
        train = df[w <= cuts[0]]
        valid = df[(w > cuts[0]) & (w <= cuts[1])]
        test = df[w > cuts[1]]
    return train, valid, test


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred) if len(y_true) > 1 else float("nan")
    denom = np.maximum(np.abs(y_true), 1e-3)
    wmape = 100.0 * np.sum(np.abs(y_true - y_pred)) / np.sum(denom)
    return {"MAE": mae, "RMSE": rmse, "R2": r2, "WMAPE": wmape}


def train_all(cfg: Optional[dict] = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    rs = cfg["models"]["random_state"]
    effort, source = load_effort(cfg, allow_demo=True)
    weekly = to_weekly_grid(effort, cfg)
    save_weekly(weekly, cfg)
    feat = build_features(weekly)
    train, valid, test = chronological_split(feat, cfg)

    X_train, y_train = train[FEATURE_COLS], train["fishing_hours_next_week"]
    X_valid, y_valid = valid[FEATURE_COLS], valid["fishing_hours_next_week"]
    X_test, y_test = test[FEATURE_COLS], test["fishing_hours_next_week"]

    # Model 0: naive = lag-1 (previous week hours as next-week prediction)
    naive_pred = X_test["fishing_hours_lag_1"].to_numpy()
    naive_mean4 = X_test["fishing_hours_rolling_mean_4"].to_numpy()

    models = {
        "Naive_lag1": None,
        "Naive_mean4": None,
        "Ridge": Ridge(alpha=1.0, random_state=rs),
        "RandomForest": RandomForestRegressor(
            n_estimators=cfg["models"]["n_estimators"],
            max_depth=cfg["models"]["max_depth"],
            random_state=rs,
            n_jobs=-1,
        ),
        "HistGBM": GradientBoostingRegressor(
            random_state=rs,
            max_depth=3,
            n_estimators=cfg["models"]["n_estimators"],
        ),
    }

    rows = []
    fitted = {}
    for name, model in models.items():
        if name == "Naive_lag1":
            pred = naive_pred
        elif name == "Naive_mean4":
            pred = naive_mean4
        else:
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            fitted[name] = model
        m = metrics(y_test, pred)
        m["Model"] = name
        m["n_test"] = len(y_test)
        rows.append(m)

    comparison = pd.DataFrame(rows)[["Model", "MAE", "RMSE", "R2", "WMAPE", "n_test"]]
    comparison = comparison.sort_values("MAE")
    out_csv = ROOT / cfg["paths"]["comparison_csv"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(out_csv, index=False)

    # Best ML model that beats naive lag1 on MAE when possible
    naive_mae = float(comparison.loc[comparison["Model"] == "Naive_lag1", "MAE"].iloc[0])
    ml = comparison[~comparison["Model"].str.startswith("Naive")]
    best_name = ml.sort_values("MAE").iloc[0]["Model"]
    best_mae = float(ml.sort_values("MAE").iloc[0]["MAE"])
    best_model = fitted[best_name]

    models_dir = ROOT / cfg["paths"]["models_dir"]
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, models_dir / "best_model.joblib")
    joblib.dump(FEATURE_COLS, models_dir / "feature_cols.joblib")
    meta = {
        "data_source": source,
        "best_model": best_name,
        "best_mae": best_mae,
        "naive_lag1_mae": naive_mae,
        "beats_naive": bool(best_mae < naive_mae),
        "feature_importance": {},
    }
    if hasattr(best_model, "feature_importances_"):
        meta["feature_importance"] = {
            f: float(v)
            for f, v in sorted(
                zip(FEATURE_COLS, best_model.feature_importances_),
                key=lambda x: -x[1],
            )[:12]
        }
    elif hasattr(best_model, "coef_"):
        meta["feature_importance"] = {
            f: float(abs(v))
            for f, v in sorted(
                zip(FEATURE_COLS, best_model.coef_),
                key=lambda x: -abs(x[1]),
            )[:12]
        }
    (models_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Predictions for latest week in feature table (forecast next week)
    latest_week = feat["week_start"].max()
    latest = feat[feat["week_start"] == latest_week].copy()
    latest["predicted_fishing_hours"] = best_model.predict(latest[FEATURE_COLS])
    latest["recent_fishing_hours"] = latest["fishing_hours"]
    base = seasonal_baseline(train)
    risk_cfg = cfg["risk"]
    scored = risk_from_prediction(
        latest,
        base,
        low_max=risk_cfg["low_max_percentile"],
        medium_max=risk_cfg["medium_max_percentile"],
        epsilon=risk_cfg["epsilon"],
    )
    pred_path = ROOT / cfg["paths"]["predictions_csv"]
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    keep = [
        "grid_id",
        "week_start",
        "lat",
        "lon",
        "recent_fishing_hours",
        "predicted_fishing_hours",
        "historical_baseline",
        "absolute_change",
        "percent_change",
        "risk_score",
        "risk_category",
    ]
    scored[keep].to_csv(pred_path, index=False)
    print(comparison.to_string(index=False))
    print(f"best={best_name} beats_naive={meta['beats_naive']} source={source}")
    print(f"wrote {out_csv}")
    print(f"wrote {pred_path}")
    return comparison


if __name__ == "__main__":
    logging_fmt = "%(levelname)s %(message)s"
    import logging

    logging.basicConfig(level=logging.INFO, format=logging_fmt)
    train_all()
