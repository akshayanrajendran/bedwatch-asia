"""Spatial-temporal aggregation to weekly grid cells."""
from __future__ import annotations

from typing import List, Optional, Tuple

from pathlib import Path

import pandas as pd

from .config_loader import ROOT, load_config


def snap_coord(values: pd.Series, origin: float, res: float) -> pd.Series:
    return origin + ((values - origin) / res).floordiv(1) * res + res / 2.0


def to_weekly_grid(df: pd.DataFrame, cfg: Optional[dict] = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    r = cfg["region"]
    res = cfg["grid"]["resolution_deg"]
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out["week"] = out["date"].dt.to_period("W-MON").dt.start_time
    out["lat"] = snap_coord(out["lat"], r["lat_min"], res)
    out["lon"] = snap_coord(out["lon"], r["lon_min"], res)
    agg = (
        out.groupby(["week", "lat", "lon"], as_index=False)["fishing_hours"]
        .sum()
        .rename(columns={"week": "week_start"})
    )
    agg["grid_id"] = (
        agg["lat"].round(3).astype(str) + "_" + agg["lon"].round(3).astype(str)
    )
    return agg.sort_values(["grid_id", "week_start"]).reset_index(drop=True)


def save_weekly(df: pd.DataFrame, cfg: Optional[dict] = None) -> Path:
    cfg = cfg or load_config()
    path = ROOT / cfg["paths"]["processed_weekly"]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
