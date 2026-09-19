"""BedWatch Asia: forecast fishing-bed risk from inappropriate bottom trawling."""
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

# CONFIG: edit lookups here. Vulnerability and recovery are illustrative placeholders
# inspired by Hiddink et al. 2017 (depletion vs penetration, recovery vs longevity).
CELL = 0.25
YEAR0, YEAR1 = 2018, 2023
VULN = {"lt20": 0.5, "20_50": 0.6, "50_100": 0.8, "gt100": 1.0}
RECOV = {"lt20": 0.8, "20_50": 0.6, "50_100": 0.4, "gt100": 0.2}
# Procedure multipliers on depletion (d) or sweep rate (f).
GEAR_D = {"otter": 0.06, "otter_heavy": 0.11, "beam": 0.14, "samba_push": 0.20}
HABITAT_D = {"mud": 1.0, "sand": 1.15, "seagrass": 3.4, "nursery_mud": 1.4}
HABITAT_R = {"mud": 0.65, "sand": 0.40, "seagrass": 0.16, "nursery_mud": 0.35}
REGIONS = {
    "thailand": {
        "title": "Gulf of Thailand",
        "lat_min": 5.0,
        "lat_max": 14.0,
        "lon_min": 99.0,
        "lon_max": 106.0,
        "center": (9.5, 102.5),
        "zoom": 5.4,
        "box": (9.0, 11.0, 100.0, 102.0),
        "depth_center": (9.0, 102.0),
        "hotspots": np.array([[8.4, 100.2], [12.0, 100.8], [10.2, 100.4], [6.6, 100.9], [13.2, 100.6]]),
        "default_gear": "otter_heavy",
    },
    "scs": {
        "title": "South China Sea (incl. Thai waters)",
        "lat_min": 2.0,
        "lat_max": 23.0,
        "lon_min": 99.0,
        "lon_max": 121.0,
        "center": (12.0, 110.5),
        "zoom": 4.2,
        "box": (9.0, 11.0, 100.0, 102.0),
        "depth_center": (12.0, 113.0),
        "hotspots": np.array(
            [
                [8.4, 100.2],
                [12.0, 100.8],
                [10.2, 100.4],
                [9.5, 106.4],
                [16.0, 108.4],
                [20.6, 107.3],
                [4.2, 108.2],
                [10.5, 114.0],
                [10.8, 118.8],
                [15.4, 119.6],
            ]
        ),
        "default_gear": "otter_heavy",
    },
}
ROOT = Path(__file__).resolve().parent
GFW = ROOT / "data" / "gfw_trawl_effort.csv"
GEBCO = ROOT / "data" / "gebco.nc"
SEAGRASS_PTS = ROOT / "data" / "seagrass_unep_palk_pts.geojson"


def cell_centers(reg):
    lats = np.arange(reg["lat_min"], reg["lat_max"], CELL) + CELL / 2
    lons = np.arange(reg["lon_min"], reg["lon_max"], CELL) + CELL / 2
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


def load_seagrass_cells(grid):
    if not SEAGRASS_PTS.exists():
        return np.zeros(len(grid), dtype=bool)
    import json

    geo = json.loads(SEAGRASS_PTS.read_text())
    pts = np.array([f["geometry"]["coordinates"] for f in geo["features"]])
    if not len(pts):
        return np.zeros(len(grid), dtype=bool)
    mask = np.zeros(len(grid), dtype=bool)
    for i, row in grid.iterrows():
        d2 = (pts[:, 1] - row["lat"]) ** 2 + (pts[:, 0] - row["lon"]) ** 2
        mask[i] = d2.min() <= (0.35**2)
    return mask


@st.cache_data
def load_effort(region_id):
    reg = REGIONS[region_id]
    grid = cell_centers(reg)
    if GFW.exists():
        raw = pd.read_csv(GFW)
        raw["year"] = pd.to_datetime(raw["date"]).dt.year
        raw = raw[
            (raw["lat"] >= reg["lat_min"])
            & (raw["lat"] <= reg["lat_max"])
            & (raw["lon"] >= reg["lon_min"])
            & (raw["lon"] <= reg["lon_max"])
        ]
        if len(raw):
            raw["lat"] = snap(raw["lat"], reg["lat_min"])
            raw["lon"] = snap(raw["lon"], reg["lon_min"])
            agg = raw.groupby(["year", "lat", "lon"], as_index=False)["fishing_hours"].sum()
            return "GFW data", agg
    rng = np.random.default_rng(42 if region_id == "thailand" else 11)
    rows = []
    for yi, year in enumerate(range(YEAR0, YEAR1 + 1)):
        hs = reg["hotspots"] + np.array([0.04 * yi, 0.03 * yi])
        hours = rng.uniform(0.2, 3.0, len(grid))
        for hlat, hlon in hs:
            dist2 = (grid["lat"] - hlat) ** 2 + (grid["lon"] - hlon) ** 2
            hours = hours + 90 * np.exp(-dist2 / (2 * 0.35**2))
        tmp = grid.copy()
        tmp["year"] = year
        tmp["fishing_hours"] = hours
        rows.append(tmp)
    return "Synthetic data", pd.concat(rows, ignore_index=True)


@st.cache_data
def load_depth(region_id):
    reg = REGIONS[region_id]
    grid = cell_centers(reg)
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
        grid["depth"] = np.clip(np.where(elev < 0, -elev, elev), 8, None)
    else:
        cy, cx = reg["depth_center"]
        dist = np.sqrt((grid["lat"] - cy) ** 2 + (grid["lon"] - cx) ** 2)
        grid["depth"] = 10 + 160 * (1 - dist / max(float(dist.max()), 0.01))
        if region_id == "thailand":
            grid["depth"] = np.clip(grid["depth"], 8, 80)
    if region_id == "thailand":
        grass = (grid["depth"] < 50) & (grid["lon"] < 102.5)
    else:
        thai_viet_shelf = grid["lon"] < 108.5
        palawan = (grid["lon"] > 116.5) & (grid["lat"] > 7) & (grid["lat"] < 13)
        grass = (thai_viet_shelf | palawan) & (grid["depth"] < 90)
    grid["habitat"] = np.where(grass, "seagrass", np.where(grid["depth"] < 50, "nursery_mud", "mud"))
    return grid


def with_lookups(df):
    keys = df["depth"].map(band_key)
    out = df.copy()
    out["vulnerability"] = keys.map(VULN)
    out["recovery"] = keys.map(RECOV)
    seag = out["habitat"] == "seagrass"
    out.loc[seag, "vulnerability"] = 0.95
    out.loc[seag, "recovery"] = 0.20
    return out


def procedure_factor(practices, habitat):
    d = GEAR_D["otter_heavy"] * HABITAT_D.get(habitat, 1.0)
    if practices.get("tickler_chains"):
        d *= 1.55
    if practices.get("high_tow_speed"):
        d *= 1.12
    if practices.get("too_shallow_on_bed") and habitat == "seagrass":
        d *= 1.28
    f = 1.45 if practices.get("repeat_same_tracks") else 1.0
    spawn = 0.62 if practices.get("spawn_season_tows") else 1.0
    return float(np.clip(d * f / spawn, 0.05, 4.0))


def apply_practices(df, practices, no_tow_seagrass=False):
    out = df.copy()
    fac = out["habitat"].map(lambda h: procedure_factor(practices, h))
    out["fishing_hours"] = out["fishing_hours"] * fac
    if no_tow_seagrass:
        out.loc[out["habitat"] == "seagrass", "fishing_hours"] = 0.0
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


def rbs_path(status0, f, d, r, years=10):
    s = float(np.clip(status0, 0, 1))
    out = [s]
    for _ in range(years):
        s = s * ((1.0 - d) ** f)
        s = s + r * (1.0 - s)
        s = float(np.clip(s, 0, 1))
        out.append(s)
    return out


def mean_rbs_inputs(df, practices):
    hours = float(df["fishing_hours"].mean())
    hab = df["habitat"].mode().iloc[0] if len(df) else "mud"
    d = GEAR_D["otter_heavy"] * HABITAT_D.get(hab, 1.0)
    if practices.get("tickler_chains"):
        d *= 1.55
    if practices.get("too_shallow_on_bed") and hab == "seagrass":
        d *= 1.28
    d = float(np.clip(d, 0.01, 0.92))
    f = max(0.0, hours / 25.0)
    if practices.get("repeat_same_tracks"):
        f *= 1.45
    r = HABITAT_R.get(hab, 0.4)
    status0 = float(np.clip(1.0 - df["risk"].mean() / 100.0, 0.05, 0.95))
    return status0, f, d, r


def deck_map(df, reg, radius=48):
    view = pdk.ViewState(
        latitude=reg["center"][0], longitude=reg["center"][1], zoom=reg["zoom"], pitch=0
    )
    heat = pdk.Layer(
        "HeatmapLayer",
        data=df,
        get_position=["lon", "lat"],
        get_weight="risk",
        radiusPixels=radius,
    )
    grass = df[df["habitat"] == "seagrass"] if "habitat" in df.columns else df.iloc[0:0]
    dots = pdk.Layer(
        "ScatterplotLayer",
        data=grass,
        get_position=["lon", "lat"],
        get_radius=3500,
        get_fill_color=[45, 140, 90, 90],
        pickable=True,
    )
    return pdk.Deck(
        layers=[heat, dots],
        initial_view_state=view,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={"text": "risk {risk}"},
    )


@st.cache_data
def build_panel(region_id):
    label, effort = load_effort(region_id)
    depth = load_depth(region_id)
    frames = []
    for year in range(YEAR0, YEAR1 + 1):
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
    st.set_page_config(page_title="BedWatch Asia", layout="wide")
    st.title("BedWatch Asia")
    st.caption(
        "SDG 14 screening tool for Thailand and the South China Sea: where inappropriate "
        "bottom trawling degrades fishing beds, and whether a closure or a gear reform "
        "actually lowers risk after boats move. Optional GFW trawler hours via GFW_API_TOKEN. "
        "Setup walkthrough: sidebar → **Setup & docs**."
    )
    region_id = st.sidebar.selectbox(
        "Waterbody",
        list(REGIONS.keys()),
        format_func=lambda k: REGIONS[k]["title"],
    )
    reg = REGIONS[region_id]
    label, all_df, hmin, hmax, rmax = build_panel(region_id)
    year = st.sidebar.slider("Year", YEAR0, YEAR1, YEAR1)
    st.sidebar.markdown(f"**{label}**")
    st.sidebar.subheader("Inappropriate procedures (current)")
    practices = {
        "tickler_chains": st.sidebar.checkbox("Tickler chains / extra groundgear", True),
        "too_shallow_on_bed": st.sidebar.checkbox("Tow too shallow on the bed", True),
        "repeat_same_tracks": st.sidebar.checkbox("Repeat the same tracks", True),
        "spawn_season_tows": st.sidebar.checkbox("Tow in spawn / nursery season", True),
        "high_tow_speed": st.sidebar.checkbox("High tow speed", False),
    }
    no_tow = st.sidebar.checkbox("Reform: no towed gear on seagrass cells", True)
    st.sidebar.subheader("Closure box")
    db = reg["box"]
    min_lat = st.sidebar.number_input("min lat", reg["lat_min"], reg["lat_max"], db[0], CELL)
    max_lat = st.sidebar.number_input("max lat", reg["lat_min"], reg["lat_max"], db[1], CELL)
    min_lon = st.sidebar.number_input("min lon", reg["lon_min"], reg["lon_max"], db[2], CELL)
    max_lon = st.sidebar.number_input("max lon", reg["lon_min"], reg["lon_max"], db[3], CELL)
    disp = st.sidebar.slider("displacement %", 0, 100, 60)
    box = (min_lat, max_lat, min_lon, max_lon)

    base_hours = all_df[all_df["year"] == year].copy()
    current = apply_practices(base_hours, practices, no_tow_seagrass=False)
    current, _ = score(current, hmin, hmax, rmax)
    reformed_p = {
        "tickler_chains": False,
        "too_shallow_on_bed": False,
        "repeat_same_tracks": False,
        "spawn_season_tows": False,
        "high_tow_speed": False,
    }
    reform = apply_practices(base_hours, reformed_p, no_tow_seagrass=no_tow)
    reform, _ = score(reform, hmin, hmax, rmax)
    closed, neigh = close_and_displace(current, box, disp)
    closed, _ = score(closed, hmin, hmax, rmax)

    before = float(current["risk"].sum())
    after_c = float(closed["risk"].sum())
    after_r = float(reform["risk"].sum())
    pct_c = 0.0 if before == 0 else 100.0 * (after_c - before) / before
    pct_r = 0.0 if before == 0 else 100.0 * (after_r - before) / before

    a, b, c, d = st.columns(4)
    a.metric("Cells", f"{len(current):,}")
    b.metric("Seagrass cells", int((current["habitat"] == "seagrass").sum()))
    c.metric("Mean risk now", f"{current['risk'].mean():.1f}")
    d.metric("Chronic share", f"{(current['risk'] >= 60).mean() * 100:.0f}%")

    m1, m2, m3 = st.columns(3)
    m1.metric("Total risk now", f"{before:.0f}")
    m2.metric("After closure", f"{after_c:.0f}", f"{pct_c:.1f}%")
    m3.metric("After procedure reform", f"{after_r:.0f}", f"{pct_r:.1f}%")

    if len(neigh) and neigh.any():
        delta = closed.loc[neigh, "risk"].to_numpy() - current.loc[neigh, "risk"].to_numpy()
        if len(delta) and np.nanmax(delta) > 20:
            st.warning(
                "Leakage: a cell next to the closure box gained more than 20 risk points. "
                "Boats moved. Pair the box with a buffer or a gear rule."
            )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader(f"Now ({year})")
        st.pydeck_chart(deck_map(current, reg), use_container_width=True)
    with c2:
        st.subheader("Closure + displacement")
        st.pydeck_chart(deck_map(closed, reg), use_container_width=True)
    with c3:
        st.subheader("Reform procedures")
        st.pydeck_chart(deck_map(reform, reg), use_container_width=True)

    st.subheader("10-year relative benthic status (mean cell)")
    s0, f, dmg, rec = mean_rbs_inputs(current, practices)
    s0r, fr, dr, recr = mean_rbs_inputs(reform, reformed_p)
    s0c, fc, dc, recc = mean_rbs_inputs(closed, practices)
    chart = pd.DataFrame(
        {
            "year": list(range(0, 11)),
            "current": rbs_path(s0, f, dmg, rec),
            "closure": rbs_path(s0c, fc, dc, recc),
            "reform": rbs_path(s0r, fr, dr, recr),
        }
    ).set_index("year")
    st.line_chart(chart)
    st.caption(
        "RBS starts from today's mean risk, then steps yearly: "
        "status = status * (1-d)^F + r * (1-status). Collapse threshold is 0.2."
    )

    st.subheader("Top 10 hotspots (current)")
    top = current.nlargest(10, "risk")[["lat", "lon", "risk", "driver", "habitat", "depth"]]
    st.dataframe(top, use_container_width=True, hide_index=True)

    with st.expander("What this is"):
        st.markdown(
            """
- **Vision:** fishing beds (seagrass, nurseries, benthos) in Asian waterbodies are scraped by
  inappropriate trawl procedures. Managers draw MPA lines. This tool scores the *bed* and tests
  whether a closure leaks effort next door, versus fixing gear, depth, and season.
- **Index:** pressure (hours, min-max over all years) x vulnerability x (1 - recovery), scaled 0-100.
- **Prediction:** 10-year RBS uses Hiddink-style depletion and recovery. Seagrass depletion is
  much higher than mud fauna (uprooting).
- Focus waterbodies: Gulf of Thailand and the South China Sea (including Thai waters).
- Drop `data/gfw_trawl_effort.csv` from `python3 model/fetch_gfw.py` (needs `GFW_API_TOKEN`)
  and optional `data/gebco.nc` to replace synthetic effort and depth.
            """
        )
    with st.expander("Limitations"):
        st.markdown(
            "- AIS gaps mean dark-fleet effort is undercounted, so true pressure is likely higher\n"
            "- habitat is a depth proxy plus UNEP points, not a full substrate map\n"
            "- recovery and vulnerability values are illustrative placeholders\n"
            "- this is a screening forecast, not a stock assessment or collapse proof"
        )


if __name__ == "__main__":
    main()
