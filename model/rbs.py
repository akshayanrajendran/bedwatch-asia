"""
Relative benthic status (RBS) for fishing beds under towed gear.

Discrete yearly model, parameterized from Hiddink et al. 2017 (depletion vs
penetration), Pitcher et al. (recovery vs longevity), and seagrass-trawl
studies in Palk Bay / SE Asia (much higher depletion than mud fauna).

This is a conservation screening model for a hackathon, not a stock assessment.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

GEAR = {
    "otter": {"d": 0.06, "label": "Otter trawl (standard doors)"},
    "otter_heavy": {"d": 0.11, "label": "Heavy otter / large doors"},
    "beam": {"d": 0.14, "label": "Beam trawl"},
    "dredge": {"d": 0.26, "label": "Dredge"},
    "samba_push": {"d": 0.20, "label": "Samba seine / push net on meadow"},
}

HABITAT = {
    "mud": {"r": 0.65, "d_mult": 1.0, "label": "Soft mud infauna"},
    "sand": {"r": 0.40, "d_mult": 1.15, "label": "Sand / mixed sediment"},
    "seagrass": {"r": 0.16, "d_mult": 3.4, "label": "Seagrass meadow (uprooting)"},
    "nursery_mud": {"r": 0.35, "d_mult": 1.4, "label": "Demersal nursery mud"},
}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def depletion_per_pass(gear: str, habitat: str, practices: dict) -> float:
    d = GEAR[gear]["d"] * HABITAT[habitat]["d_mult"]
    if practices.get("tickler_chains"):
        d *= 1.55
    if practices.get("high_tow_speed"):
        d *= 1.12
    if practices.get("too_shallow_on_bed") and habitat == "seagrass":
        d *= 1.28
    return clamp(d, 0.01, 0.92)


def effective_frequency(sweeps_per_year: float, practices: dict) -> float:
    f = max(0.0, sweeps_per_year)
    if practices.get("repeat_same_tracks"):
        f *= 1.45
    return f


def step(status: float, f: float, d: float, r: float) -> float:
    survival = (1.0 - d) ** f
    status = status * survival
    status = status + r * (1.0 - status)
    return clamp(status)


def trajectory(status0: float, years: int, f: float, d: float, r: float) -> list[float]:
    s = clamp(status0)
    out = [s]
    for _ in range(years):
        s = step(s, f, d, r)
        out.append(s)
    return out


def years_to_threshold(path: list[float], threshold: float = 0.2) -> int | None:
    for i, v in enumerate(path):
        if v < threshold:
            return i
    return None


def nursery_function(rbs: float, practices: dict) -> float:
    n = rbs
    if practices.get("spawn_season_tows"):
        n *= 0.62
    if practices.get("too_shallow_on_bed"):
        n *= 0.85
    return clamp(n)


def flags(practices: dict, habitat: str, f: float, d: float, r: float) -> list[str]:
    items = []
    if habitat == "seagrass" and d > 0.25:
        items.append("Towed gear on seagrass: shoots and rhizomes are ripped out, not just fauna reduced.")
    if practices.get("tickler_chains"):
        items.append("Tickler chains increase seafloor penetration — inappropriate on vegetated beds.")
    if practices.get("too_shallow_on_bed"):
        items.append("Towing in water too shallow for the gear; doors/footrope scour the meadow.")
    if practices.get("repeat_same_tracks"):
        items.append("Repeated tows on the same tracks raise local sweep rate above the nominal effort.")
    if practices.get("spawn_season_tows"):
        items.append("Trawling during spawning/nursery season hits bed structure and recruitment together.")
    if practices.get("high_tow_speed"):
        items.append("High tow speed increases contact force of doors and groundgear.")
    if f * d > r:
        items.append("Chronic: depletion per year exceeds the bed's recovery rate, so status trends down.")
    if not items:
        items.append("Gear, depth, and timing are within a lower-impact envelope for this habitat.")
    return items


def predict(params: dict) -> dict:
    gear = params["gear"]
    habitat = params["habitat"]
    practices = params.get("practices", {})
    f = effective_frequency(params["sweeps_per_year"], practices)
    d = depletion_per_pass(gear, habitat, practices)
    r = HABITAT[habitat]["r"]
    years = int(params.get("years", 10))
    status0 = float(params.get("status0", 1.0))
    path = trajectory(status0, years, f, d, r)
    reformed = {
        "tickler_chains": False,
        "too_shallow_on_bed": False,
        "repeat_same_tracks": False,
        "spawn_season_tows": False,
        "high_tow_speed": False,
    }
    f2 = params["sweeps_per_year"]
    d2 = depletion_per_pass("otter", habitat, reformed)
    path2 = trajectory(status0, years, f2, d2, r)
    # Bed-safe: no towed gear on seagrass/nursery cells; light otter elsewhere
    f3 = 0.0 if habitat in ("seagrass", "nursery_mud") else min(f2, 1.0)
    d3 = depletion_per_pass("otter", habitat, reformed)
    path3 = trajectory(status0, years, f3, d3, r)
    return {
        "f": round(f, 3),
        "d": round(d, 3),
        "r": r,
        "gear_label": GEAR[gear]["label"],
        "habitat_label": HABITAT[habitat]["label"],
        "rbs_now": path[0],
        "rbs_horizon": path[-1],
        "rbs_reformed": path2[-1],
        "rbs_bedsafe": path3[-1],
        "nursery_horizon": nursery_function(path[-1], practices),
        "years_to_collapse": years_to_threshold(path, 0.2),
        "path": [round(x, 4) for x in path],
        "path_reformed": [round(x, 4) for x in path2],
        "path_bedsafe": [round(x, 4) for x in path3],
        "flags": flags(practices, habitat, f, d, r),
        "chronic": f * d > r,
    }


def palk_grid() -> dict:
    """Synthetic 0.1° cells over Palk Bay with spatially varying sweep rates."""
    features = []
    # lon 78.9–79.7, lat 9.2–10.0
    lons = [78.90 + 0.1 * i for i in range(9)]
    lats = [9.20 + 0.1 * j for j in range(9)]
    for i, lon in enumerate(lons[:-1]):
        for j, lat in enumerate(lats[:-1]):
            # Higher F in the central shallow trough (classic trawl grounds)
            dist = math.hypot((lon + 0.05) - 79.25, (lat + 0.05) - 9.55)
            f = max(0.3, 7.2 * math.exp(-(dist**2) / 0.08))
            too_shallow = lat > 9.35
            practices = {
                "tickler_chains": f > 3.5,
                "too_shallow_on_bed": too_shallow and f > 1.5,
                "repeat_same_tracks": f > 4,
                "spawn_season_tows": f > 2.5,
                "high_tow_speed": False,
            }
            pred = predict(
                {
                    "gear": "otter_heavy" if f > 4 else "otter",
                    "habitat": "seagrass",
                    "sweeps_per_year": f,
                    "practices": practices,
                    "status0": 0.55,
                    "years": 10,
                }
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "forecast",
                        "hotspot": "palk-bay",
                        "sweeps": round(f, 2),
                        "rbs10": round(pred["rbs_horizon"], 4),
                        "rbs10_reformed": round(pred["rbs_reformed"], 4),
                        "rbs10_bedsafe": round(pred["rbs_bedsafe"], 4),
                        "collapse": pred["years_to_collapse"],
                        "chronic": pred["chronic"],
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon, lat],
                                [lon + 0.1, lat],
                                [lon + 0.1, lat + 0.1],
                                [lon, lat + 0.1],
                                [lon, lat],
                            ]
                        ],
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    (root / "data" / "palk_forecast.geojson").write_text(
        json.dumps(palk_grid()), encoding="utf-8"
    )
    print("wrote data/palk_forecast.geojson")


if __name__ == "__main__":
    main()
