"""Fishing Pressure Risk Score (0-100) vs seasonal historical baseline."""
from __future__ import annotations

import numpy as np
import pandas as pd


def seasonal_baseline(train_df: pd.DataFrame) -> pd.DataFrame:
    """Median fishing hours by grid_id and week-of-year from training data only."""
    t = train_df.copy()
    t["week_start"] = pd.to_datetime(t["week_start"])
    t["weekofyear"] = t["week_start"].dt.isocalendar().week.astype(int)
    base = (
        t.groupby(["grid_id", "weekofyear"], as_index=False)["fishing_hours"]
        .median()
        .rename(columns={"fishing_hours": "historical_baseline"})
    )
    return base


def risk_from_prediction(
    pred_df: pd.DataFrame,
    baseline: pd.DataFrame,
    low_max: float = 70.0,
    medium_max: float = 90.0,
    epsilon: float = 0.1,
) -> pd.DataFrame:
    out = pred_df.copy()
    if "weekofyear" not in out.columns:
        out["week_start"] = pd.to_datetime(out["week_start"])
        out["weekofyear"] = out["week_start"].dt.isocalendar().week.astype(int)
    out = out.merge(baseline, on=["grid_id", "weekofyear"], how="left")
    out["historical_baseline"] = out["historical_baseline"].fillna(
        out["predicted_fishing_hours"].median()
    )
    out["absolute_change"] = out["predicted_fishing_hours"] - out["historical_baseline"]
    out["percent_change"] = 100.0 * out["absolute_change"] / (out["historical_baseline"] + epsilon)
    out["pressure_ratio"] = out["predicted_fishing_hours"] / (out["historical_baseline"] + epsilon)
    # Percentile of pressure_ratio across this prediction set
    ranks = out["pressure_ratio"].rank(method="average", pct=True) * 100.0
    out["risk_score"] = ranks.clip(0, 100)
    out["risk_category"] = np.where(
        out["risk_score"] >= medium_max,
        "HIGH",
        np.where(out["risk_score"] >= low_max, "MEDIUM", "LOW"),
    )
    return out
