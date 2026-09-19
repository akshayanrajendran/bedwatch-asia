"""Trawl Risk Index demo: seabed ecosystem risk from bottom trawling, Gulf of Thailand."""
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

# CONFIG: all weights and lookups are easy to edit.
# Vulnerability and recovery values are illustrative placeholders.
CONFIG = {
    "lat_min": 5.0,
    "lat_max": 14.0,
    "lon_min": 99.0,
    "lon_max": 106.0,
    "cell": 0.25,
    "year0": 2018,
    "year1": 2023,
    "center_lat": 9.5,
    "center_lon": 102.5,
    "vulnerability": {"lt20": 0.5, "20_50": 0.6, "50_100": 0.8, "gt100": 1.0},
    "recovery": {"lt20": 0.8, "20_50": 0.6, "50_100": 0.4, "gt100": 0.2},
}
ROOT = Path(__file__).resolve().parent
GFW = ROOT / "data" / "gfw_trawl_effort.csv"
GEBCO = ROOT / "data" / "gebco.nc"
CELL = CONFIG["cell"]


def cell_centers():
    lats = np.arange(CONFIG["lat_min"], CONFIG["lat_max"], CELL) + CELL / 2
    lons = np.arange(CONFIG["lon_min"], CONFIG["lon_max"], CELL) + CELL / 2
    yy, xx = np.meshgrid(lats, lons, indexing="ij")
    return pd.DataFrame({"lat": yy.ravel(), "lon": xx.ravel()})


def snap(s, origin):
    return origin + np.floor((s - origin) / CELL) * CELL + CELL / 2


def band_key(depth):
    if depth < 20:
        return "lt20"
    if depth < 50:
        return "20_50"
    if depth < 100:
        return "50_100"
    return "gt100"


@st.cache_data
def load_effort():
    grid = cell_centers()
    if GFW.exists():
        raw = pd.read_csv(GFW)
        raw["year"] = pd.to_datetime(raw["date"]).dt.year
        raw["lat"] = snap(raw["lat"], CONFIG["lat_min"])
        raw["lon"] = snap(raw["lon"], CONFIG["lon_min"])
        agg = raw.groupby(["year", "lat", "lon"], as_index=False)["fishing_hours"].sum()
        return "GFW data", agg
    rng = np.random.default_rng(42)
    # Coastal hotspots (west/north gulf), drifting slightly each year.
    hotspots = np.array([[8.4, 100.2], [12.0, 100.8], [10.2, 100.4], [6.6, 100.9]])
    rows = []
    for yi, year in enumerate(range(CONFIG["year0"], CONFIG["year1"] + 1)):
        hs = hotspots + np.array([0.05 * yi, 0.04 * yi])
        hours = rng.uniform(0.2, 3.0, len(grid))
        for hlat, hlon in hs:
            dist2 = (grid["lat"] - hlat) ** 2 + (grid["lon"] - hlon) ** 2
            hours = hours + 90 * np.exp(-dist2 / (2 * 0.45**2))
        tmp = grid.copy()
        tmp["year"] = year
        tmp["fishing_hours"] = hours
        rows.append(tmp)
    return "Synthetic data", pd.concat(rows, ignore_index=True)


@st.cache_data
def load_depth():
    grid = cell_centers()
    if GEBCO.exists():
        import xarray as xr

        ds = xr.open_dataset(GEBCO)
        var = "elevation" if "elevation" in ds.data_vars else list(ds.data_vars)[0]
        da = ds[var]
        latn = "lat" if "lat" in da.coords else "latitude"
        lonn = "lon" if "lon" in da.coords else "longitude"
        pts = da.interp(
            {
                latn: xr.DataArray(grid["lat"].values, dims="p"),
                lonn: xr.DataArray(grid["lon"].values, dims="p"),
            }
        )
        elev = np.asarray(pts)
        grid["depth"] = np.clip(np.where(elev < 0, -elev, elev), 10, None)
        return grid
    # Deeper toward gulf center (~9N, 102E), roughly 10-200 m.
    dist = np.sqrt((grid["lat"] - 9.0) ** 2 + (grid["lon"] - 102.0) ** 2)
    grid["depth"] = 10 + 190 * (1 - dist / dist.max())
    return grid


def with_lookups(df):
    keys = df["depth"].map(band_key)
    out = df.copy()
    out["vulnerability"] = keys.map(CONFIG["vulnerability"])
    out["recovery"] = keys.map(CONFIG["recovery"])
    return out


def score(df, hmin, hmax, rmax=None):
    out = df.copy()
    span = hmax - hmin
    out["pressure"] = 0.0 if span == 0 else ((out["fishing_hours"] - hmin) / span).clip(0, 1)
    raw = out["pressure"] * out["vulnerability"] * (1.0 - out["recovery"])
    if rmax is None:
        rmax = float(raw.max()) if len(raw) and raw.max() > 0 else 1.0
    out["risk"] = 0.0 if rmax == 0 else 100.0 * raw / rmax
    out["driver"] = np.where(
        out["pressure"] >= out["vulnerability"], "pressure-driven", "vulnerability-driven"
    )
    return out, rmax


def in_box(df, box):
    a, b, c, d = box
    return (df["lat"] >= a) & (df["lat"] <= b) & (df["lon"] >= c) & (df["lon"] <= d)


def neighbor_mask(df, box):
    a, b, c, d = box
    ring = (
        (df["lat"] >= a - CELL)
        & (df["lat"] <= b + CELL)
        & (df["lon"] >= c - CELL)
        & (df["lon"] <= d + CELL)
    )
    return ring & ~in_box(df, box)


def close_and_displace(df, box, disp_pct):
    out = df.copy()
    inside = in_box(out, box)
    neigh = neighbor_mask(out, box)
    closed = float(out.loc[inside, "fishing_hours"].sum())
    out.loc[inside, "fishing_hours"] = 0.0
    move = closed * disp_pct / 100.0
    idx = out.index[neigh]
    if len(idx) and move > 0:
        w = out.loc[idx, "fishing_hours"].to_numpy(dtype=float)
        w = np.ones_like(w) if w.sum() <= 0 else w
        w = w / w.sum()
        out.loc[idx, "fishing_hours"] = out.loc[idx, "fishing_hours"] + move * w
    return out, neigh


def deck_map(df):
    view = pdk.ViewState(
        latitude=CONFIG["center_lat"], longitude=CONFIG["center_lon"], zoom=5.4, pitch=0
    )
    layer = pdk.Layer(
        "HeatmapLayer",
        data=df,
        get_position=["lon", "lat"],
        get_weight="risk",
        radiusPixels=48,
    )
    return pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )


@st.cache_data
def build_panel():
    label, effort = load_effort()
    depth = load_depth()
    frames = []
    for year in range(CONFIG["year0"], CONFIG["year1"] + 1):
        g = depth.copy()
        g["year"] = year
        frames.append(g)
    merged = pd.concat(frames, ignore_index=True).merge(
        effort, on=["year", "lat", "lon"], how="left"
    )
    merged["fishing_hours"] = merged["fishing_hours"].fillna(0)
    merged = with_lookups(merged)
    hmin = float(merged["fishing_hours"].min())
    hmax = float(merged["fishing_hours"].max())
    scored, rmax = score(merged, hmin, hmax)
    return label, scored, hmin, hmax, rmax


def main():
    st.set_page_config(page_title="Trawl Risk Index", layout="wide")
    st.title("Trawl Risk Index")
    st.caption("Seabed ecosystem risk from bottom trawling in the Gulf of Thailand.")
    label, all_df, hmin, hmax, rmax = build_panel()
    year = st.sidebar.slider("Year", CONFIG["year0"], CONFIG["year1"], CONFIG["year1"])
    st.sidebar.markdown(f"**{label}**")
    st.sidebar.subheader("Closure scenario")
    min_lat = st.sidebar.number_input("min lat", CONFIG["lat_min"], CONFIG["lat_max"], 9.0, 0.25)
    max_lat = st.sidebar.number_input("max lat", CONFIG["lat_min"], CONFIG["lat_max"], 11.0, 0.25)
    min_lon = st.sidebar.number_input("min lon", CONFIG["lon_min"], CONFIG["lon_max"], 100.0, 0.25)
    max_lon = st.sidebar.number_input("max lon", CONFIG["lon_min"], CONFIG["lon_max"], 102.0, 0.25)
    disp = st.sidebar.slider("displacement %", 0, 100, 60)
    box = (min_lat, max_lat, min_lon, max_lon)
    yr = all_df[all_df["year"] == year].copy()
    st.subheader(f"Risk map ({year})")
    st.pydeck_chart(deck_map(yr), use_container_width=True)
    top = yr.nlargest(10, "risk")[["lat", "lon", "risk", "driver"]]
    st.subheader("Top 10 hotspots")
    st.dataframe(top, use_container_width=True, hide_index=True)
    closed, neigh = close_and_displace(yr, box, disp)
    scen, _ = score(closed, hmin, hmax, rmax)
    before = float(yr["risk"].sum())
    after = float(scen["risk"].sum())
    pct = 0.0 if before == 0 else 100.0 * (after - before) / before
    c1, c2, c3 = st.columns(3)
    c1.metric("Total risk before", f"{before:.1f}")
    c2.metric("Total risk after", f"{after:.1f}")
    c3.metric("% change", f"{pct:.1f}%")
    delta = scen.loc[neigh, "risk"].to_numpy() - yr.loc[neigh, "risk"].to_numpy()
    if len(delta) and np.nanmax(delta) > 20:
        st.warning("A neighboring cell's risk increased by more than 20 points.")
    st.subheader("Scenario map")
    st.pydeck_chart(deck_map(scen), use_container_width=True)
    with st.expander("Limitations"):
        st.markdown(
            "- AIS gaps mean dark-fleet effort is undercounted, so true pressure is likely higher\n"
            "- habitat map is a depth proxy, not observed substrate\n"
            "- recovery values are illustrative\n"
            "- this is a screening index, not a collapse forecast"
        )


if __name__ == "__main__":
    main()
