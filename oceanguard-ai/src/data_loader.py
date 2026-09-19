"""Load Global Fishing Watch apparent fishing effort (real or DEMO)."""
from __future__ import annotations

from typing import List, Optional, Tuple

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config_loader import ROOT, load_config

logger = logging.getLogger(__name__)

# Official GFW fleet v3 columns (when present)
GFW_FLEET_COLS = {"date", "lat_bin", "lon_bin", "fishing_hours"}
SIMPLE_COLS = {"date", "lat", "lon", "fishing_hours"}


def _find_raw_files(raw_dir: Path) -> List[Path]:
    files = []
    for pattern in ("*.csv", "*.CSV"):
        files.extend(sorted(raw_dir.glob(pattern)))
    # Prefer real downloads over demo
    real = [p for p in files if "demo" not in p.name.lower()]
    return real if real else files


def _normalize_gfw(df: pd.DataFrame, resolution_hint: float = 0.1) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    df = df.rename(columns={cols[k]: k for k in cols})
    df.columns = [c.lower() for c in df.columns]

    if {"lat_bin", "lon_bin"}.issubset(df.columns):
        # lat_bin / lon_bin are lower-left edges. Convert to cell centers.
        # Values may be degrees or integer tenths/hundredths.
        lat = df["lat_bin"].astype(float)
        lon = df["lon_bin"].astype(float)
        if lat.abs().max() > 90:
            lat = lat / 10.0
            lon = lon / 10.0
            if lat.abs().max() > 90:
                lat = df["lat_bin"].astype(float) / 100.0
                lon = df["lon_bin"].astype(float) / 100.0
                resolution_hint = 0.01
            else:
                resolution_hint = 0.1
        df["lat"] = lat + resolution_hint / 2.0
        df["lon"] = lon + resolution_hint / 2.0
    elif not {"lat", "lon"}.issubset(df.columns):
        raise ValueError(
            "CSV must have (lat, lon) or GFW (lat_bin, lon_bin) columns. "
            f"Found: {list(df.columns)}"
        )

    if "fishing_hours" not in df.columns:
        raise ValueError("CSV must include fishing_hours")

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"], errors="coerce"),
            "lat": pd.to_numeric(df["lat"], errors="coerce"),
            "lon": pd.to_numeric(df["lon"], errors="coerce"),
            "fishing_hours": pd.to_numeric(df["fishing_hours"], errors="coerce"),
        }
    )
    if "geartype" in df.columns:
        out["geartype"] = df["geartype"].astype(str)
    if "flag" in df.columns:
        out["flag"] = df["flag"].astype(str)
    return out


def quality_filter(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.dropna(subset=["date", "lat", "lon", "fishing_hours"])
    df = df[(df["lat"] >= -90) & (df["lat"] <= 90)]
    df = df[(df["lon"] >= -180) & (df["lon"] <= 180)]
    df = df[df["fishing_hours"] >= 0]
    r = cfg["region"]
    df = df[
        (df["lat"] >= r["lat_min"])
        & (df["lat"] <= r["lat_max"])
        & (df["lon"] >= r["lon_min"])
        & (df["lon"] <= r["lon_max"])
    ]
    n1 = len(df)
    logger.info("quality_filter removed %s / %s rows", n0 - n1, n0)
    return df.reset_index(drop=True)


def generate_demo_effort(cfg: dict) -> pd.DataFrame:
    """DEMO DATA only — realistic weekly effort for UI/pipeline testing."""
    rng = np.random.default_rng(42)
    r = cfg["region"]
    res = cfg["grid"]["resolution_deg"]
    lats = np.arange(r["lat_min"], r["lat_max"], res) + res / 2
    lons = np.arange(r["lon_min"], r["lon_max"], res) + res / 2
    weeks = pd.date_range(cfg["time"]["start_date"], cfg["time"]["end_date"], freq="W-MON")
    # Coastal hotspots in Gulf of St. Lawrence
    hotspots = np.array([[48.5, -64.0], [49.2, -66.0], [47.8, -61.5], [50.0, -63.5], [46.5, -62.0]])
    rows = []
    for w in weeks:
        for lat in lats:
            for lon in lons:
                dist2 = ((hotspots[:, 0] - lat) ** 2 + (hotspots[:, 1] - lon) ** 2).min()
                season = 1.0 + 0.45 * np.sin(2 * np.pi * (w.dayofyear / 365.25) - 0.8)
                base = 2.0 + 40.0 * np.exp(-dist2 / (2 * 0.8**2))
                noise = rng.uniform(0.5, 1.4)
                hours = max(0.0, base * season * noise)
                if hours < 1.5 and rng.random() > 0.35:
                    continue
                rows.append(
                    {
                        "date": w,
                        "lat": float(lat),
                        "lon": float(lon),
                        "fishing_hours": float(hours),
                        "geartype": "trawlers" if rng.random() > 0.4 else "other_fishing",
                        "flag": "CAN",
                    }
                )
    df = pd.DataFrame(rows)
    df.attrs["source"] = "DEMO"
    return df


def load_effort(cfg: Optional[dict] = None, allow_demo: bool = True) -> Tuple[pd.DataFrame, str]:
    cfg = cfg or load_config()
    raw_dir = ROOT / cfg["paths"]["raw_dir"]
    files = _find_raw_files(raw_dir)
    demo_path = raw_dir / "demo_gfw_effort.csv"

    if files and "demo" not in files[0].name.lower():
        frames = []
        for path in files:
            if "demo" in path.name.lower():
                continue
            part = pd.read_csv(path)
            frames.append(_normalize_gfw(part))
        if frames:
            df = pd.concat(frames, ignore_index=True)
            df = quality_filter(df, cfg)
            return df, "GFW data"

    if allow_demo:
        if demo_path.exists():
            df = _normalize_gfw(pd.read_csv(demo_path))
            df = quality_filter(df, cfg)
        else:
            df = generate_demo_effort(cfg)
            demo_path.parent.mkdir(parents=True, exist_ok=True)
            out = df.copy()
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            out.to_csv(demo_path, index=False)
        return df, "DEMO DATA"

    raise FileNotFoundError(
        f"No GFW CSV in {raw_dir}. See data/raw/README.md or set allow_demo=True."
    )
