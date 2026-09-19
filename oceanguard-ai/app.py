"""OceanGuard AI Streamlit dashboard — next-week fishing pressure forecast."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import load_config
from src.train import train_all

try:
    st.set_page_config(page_title="OceanGuard AI", layout="wide")
except st.errors.StreamlitAPIException:
    # Already configured by a parent Streamlit multipage host
    pass


@st.cache_data(show_spinner=False)
def load_predictions():
    cfg = load_config()
    pred_path = ROOT / cfg["paths"]["predictions_csv"]
    cmp_path = ROOT / cfg["paths"]["comparison_csv"]
    meta_path = ROOT / cfg["paths"]["models_dir"] / "meta.json"
    if not pred_path.exists() or not cmp_path.exists():
        return None, None, None, cfg
    preds = pd.read_csv(pred_path)
    comparison = pd.read_csv(cmp_path)
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return preds, comparison, meta, cfg


def risk_color(cat: str):
    return {
        "LOW": [46, 160, 67, 160],
        "MEDIUM": [240, 180, 41, 180],
        "HIGH": [200, 55, 45, 200],
    }.get(cat, [120, 120, 120, 160])


def main():
    st.sidebar.markdown("**Suite:** BedWatch seabed risk · OceanGuard pressure forecast")
    st.title("OceanGuard AI")
    st.caption("Fishing Pressure Forecast & Hotspot Detection · SDG 14 — Life Below Water")
    st.info(
        "Predicts **future apparent fishing pressure** relative to history for the "
        "**Gulf of Thailand / South China Sea** (same BedWatch geography). "
        "Does **not** claim illegal fishing, overfishing, or ecological damage. "
        "When only annual GFW cells are available, hours are seasonally spread to weeks for the pipeline."
    )

    preds, comparison, meta, cfg = load_predictions()
    if preds is None:
        st.warning("No trained model yet. Click train (uses DEMO DATA if no GFW CSV is present).")
        if st.button("Train models now"):
            with st.spinner("Training…"):
                train_all(cfg)
            st.cache_data.clear()
            st.rerun()
        return

    source = meta.get("data_source", "unknown")
    badge = "DEMO DATA" if "DEMO" in str(source).upper() else str(source)
    st.sidebar.markdown(f"**Data:** `{badge}`")
    st.sidebar.markdown(f"**Region:** {cfg['region']['name']}")
    st.sidebar.markdown(f"**Best model:** {meta.get('best_model', '—')}")
    if st.sidebar.button("Retrain"):
        with st.spinner("Training…"):
            train_all(cfg)
        st.cache_data.clear()
        st.rerun()

    high_n = int((preds["risk_category"] == "HIGH").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Predicted fishing hours", f"{preds['predicted_fishing_hours'].sum():,.0f}")
    c2.metric(
        "Change vs baseline",
        f"{preds['absolute_change'].sum():,.0f} h",
        f"{preds['percent_change'].mean():+.1f}% mean",
    )
    c3.metric("HIGH-risk cells", high_n)
    c4.metric("Highest risk score", f"{preds['risk_score'].max():.0f}")

    preds = preds.copy()
    preds["color"] = preds["risk_category"].map(risk_color)
    view = pdk.ViewState(
        latitude=float(preds["lat"].mean()),
        longitude=float(preds["lon"].mean()),
        zoom=5.2,
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=preds,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius=12000,
        pickable=True,
    )
    st.subheader("Predicted fishing-pressure risk map")
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip={
                "text": "Risk {risk_category} ({risk_score})\n"
                "Predicted {predicted_fishing_hours} h\n"
                "Baseline {historical_baseline} h\n"
                "Change {percent_change}%"
            },
        ),
        use_container_width=True,
    )

    st.subheader("Top emerging fishing-pressure hotspots")
    top = preds.nlargest(10, "risk_score")[
        [
            "lat",
            "lon",
            "predicted_fishing_hours",
            "historical_baseline",
            "percent_change",
            "risk_score",
            "risk_category",
        ]
    ].reset_index(drop=True)
    top.index = top.index + 1
    top.index.name = "Rank"
    st.dataframe(top, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Model performance (held-out test)")
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        if meta.get("beats_naive"):
            st.success("Best ML model beats naive lag-1 baseline on MAE.")
        else:
            st.warning("Best ML model does not beat naive lag-1 on MAE — trust the baseline more.")
    with right:
        st.subheader("Why higher pressure? (feature importance)")
        imp = meta.get("feature_importance") or {}
        if imp:
            imp_df = pd.DataFrame({"feature": list(imp.keys()), "importance": list(imp.values())})
            st.bar_chart(imp_df.set_index("feature"))
            drivers = list(imp.keys())[:3]
            st.markdown(
                "Main drivers (model features):\n"
                + "\n".join(f"{i+1}. `{d}`" for i, d in enumerate(drivers))
            )
        else:
            st.write("Feature importance unavailable for this model type.")

    with st.expander("About / methodology"):
        st.markdown(
            f"""
- **SDG 14:** early-warning view of where *apparent* fishing activity may concentrate next week.
- **Data:** Global Fishing Watch apparent fishing effort schema (or clearly marked DEMO DATA).
- **Unit:** 0.5° grid cell × week → predict `fishing_hours_next_week`.
- **Models:** naive lag / 4-week mean, Ridge, Random Forest, Gradient Boosting; chronological train/valid/test.
- **Risk score 0–100:** how unusually high the prediction is vs seasonal historical median for that cell
  (percentile of pressure ratio). **Not** probability of illegal fishing.
- **Region:** {cfg['region']['name']}
- **Limitations:** AIS undercounts vessels without AIS; high hours ≠ overfishing or ecological harm.
  Ecological assessment needs stocks, catch, quotas, and regulations.
            """
        )


if __name__ == "__main__":
    main()
