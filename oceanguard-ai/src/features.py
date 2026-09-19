"""Feature engineering for next-week fishing-hours forecast (no leakage)."""
from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_COLS = [
    "lat",
    "lon",
    "weekofyear",
    "month",
    "year",
    "sin_week",
    "cos_week",
    "fishing_hours_lag_1",
    "fishing_hours_lag_2",
    "fishing_hours_lag_3",
    "fishing_hours_lag_4",
    "fishing_hours_rolling_mean_4",
    "fishing_hours_rolling_std_4",
    "fishing_hours_rolling_max_4",
    "fishing_hours_rolling_mean_8",
    "delta_1",
]


def build_features(weekly: pd.DataFrame) -> pd.DataFrame:
    df = weekly.sort_values(["grid_id", "week_start"]).copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df["weekofyear"] = df["week_start"].dt.isocalendar().week.astype(int)
    df["month"] = df["week_start"].dt.month
    df["year"] = df["week_start"].dt.year
    ang = 2 * np.pi * df["weekofyear"] / 52.0
    df["sin_week"] = np.sin(ang)
    df["cos_week"] = np.cos(ang)

    g = df.groupby("grid_id", group_keys=False)
    for k in (1, 2, 3, 4):
        df[f"fishing_hours_lag_{k}"] = g["fishing_hours"].shift(k)
    roll = g["fishing_hours"]
    df["fishing_hours_rolling_mean_4"] = roll.transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).mean()
    )
    df["fishing_hours_rolling_std_4"] = roll.transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).std()
    ).fillna(0.0)
    df["fishing_hours_rolling_max_4"] = roll.transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).max()
    )
    df["fishing_hours_rolling_mean_8"] = roll.transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).mean()
    )
    df["delta_1"] = df["fishing_hours_lag_1"] - df["fishing_hours_lag_2"]
    # Target: next week's hours (same grid)
    df["fishing_hours_next_week"] = g["fishing_hours"].shift(-1)
    df = df.dropna(subset=["fishing_hours_lag_1", "fishing_hours_next_week"]).reset_index(
        drop=True
    )
    # Early weeks still lack deeper lags; models need finite features
    df[FEATURE_COLS] = df[FEATURE_COLS].fillna(0.0)
    return df
