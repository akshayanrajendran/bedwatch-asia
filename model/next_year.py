"""Next-year trawl-hours forecast from annual GFW cells (BedWatch Asia)."""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score


FEATURE_COLS = [
    "hours_lag1",
    "hours_lag2",
    "hours_delta",
    "hours_mean3",
    "lat",
    "lon",
]


def _cell_panel(effort: pd.DataFrame) -> pd.DataFrame:
    """Build lagged panel: features at year t predict fishing_hours at t+1."""
    df = effort.copy()
    df["lat"] = df["lat"].round(3)
    df["lon"] = df["lon"].round(3)
    df = df.groupby(["year", "lat", "lon"], as_index=False)["fishing_hours"].sum()
    df = df.sort_values(["lat", "lon", "year"])
    parts = []
    for _, g in df.groupby(["lat", "lon"]):
        g = g.sort_values("year").copy()
        g["hours_lag1"] = g["fishing_hours"]
        g["hours_lag2"] = g["fishing_hours"].shift(1)
        g["hours_delta"] = g["hours_lag1"] - g["hours_lag2"]
        g["hours_mean3"] = g["fishing_hours"].rolling(3, min_periods=1).mean()
        g["target_next"] = g["fishing_hours"].shift(-1)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def train_next_year(effort: pd.DataFrame):
    panel = _cell_panel(effort)
    train = panel.dropna(subset=["target_next"]).copy()
    train["hours_lag2"] = train["hours_lag2"].fillna(train["hours_lag1"])
    train["hours_delta"] = train["hours_delta"].fillna(0.0)

    years = sorted(train["year"].unique())
    if len(years) < 2:
        raise ValueError("Need at least two years of effort history to train.")

    test_year = years[-1]
    tr = train[train["year"] < test_year]
    te = train[train["year"] == test_year]
    if len(tr) < 30:
        cut = int(0.8 * len(train))
        tr, te = train.iloc[:cut], train.iloc[cut:]

    model = GradientBoostingRegressor(
        random_state=42, max_depth=3, n_estimators=80, learning_rate=0.08
    )
    model.fit(tr[FEATURE_COLS], tr["target_next"])
    pred = model.predict(te[FEATURE_COLS])
    metrics = {
        "test_year": int(te["year"].iloc[0]) if len(te) else int(test_year),
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "mae": float(mean_absolute_error(te["target_next"], pred)),
        "r2": float(r2_score(te["target_next"], pred)) if len(te) > 1 else float("nan"),
        "naive_mae": float(mean_absolute_error(te["target_next"], te["hours_lag1"])),
    }
    metrics["beats_naive"] = bool(metrics["mae"] < metrics["naive_mae"])
    return model, metrics, panel


def forecast_next_year(effort: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """Predict hours for (latest_year + 1) for every cell observed in the latest year."""
    model, metrics, panel = train_next_year(effort)
    latest = int(effort["year"].max())
    feat = panel[panel["year"] == latest].copy()
    feat["hours_lag2"] = feat["hours_lag2"].fillna(feat["hours_lag1"])
    feat["hours_delta"] = feat["hours_delta"].fillna(0.0)
    feat["predicted_hours"] = np.clip(model.predict(feat[FEATURE_COLS]), 0, None)
    feat["forecast_year"] = latest + 1
    feat["change"] = feat["predicted_hours"] - feat["hours_lag1"]
    feat["pct_change"] = 100.0 * feat["change"] / (feat["hours_lag1"] + 1e-3)
    out = feat[
        [
            "lat",
            "lon",
            "forecast_year",
            "hours_lag1",
            "predicted_hours",
            "change",
            "pct_change",
        ]
    ].rename(columns={"hours_lag1": "hours_last_year"})
    metrics["forecast_year"] = latest + 1
    metrics["n_forecast_cells"] = int(len(out))
    return out, metrics
