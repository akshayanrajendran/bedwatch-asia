# Refresh UNEP-WCMC seagrass extract for Palk Bay / Gulf of Mannar.
# No API key. Envelope: 78.0–81.5 E, 8.0–11.0 N.

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://data-gis.unep-wcmc.org/server/rest/services/HabitatsAndBiotopes/Global_Distribution_of_Seagrasses/FeatureServer"
ENVELOPE = "78.0,8.0,81.5,11.0"
ROOT = Path(__file__).resolve().parents[1]


def query(layer: int, record_count: int) -> dict:
    params = {
        "geometry": ENVELOPE,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "objectid",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": str(record_count),
    }
    url = f"{BASE}/{layer}/query?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def simplify_ring(ring: list, target: int = 80) -> list:
    step = max(1, len(ring) // target)
    pts = ring[::step]
    if pts[-1] != ring[-1]:
        pts.append(ring[-1])
    return pts


def slim_poly(fc: dict) -> dict:
    out = {"type": "FeatureCollection", "name": "unep-wcmc-seagrass-palk-mannar", "features": []}
    for feat in fc.get("features", []):
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            geom = {"type": "Polygon", "coordinates": [simplify_ring(r) for r in geom["coordinates"]]}
        elif geom["type"] == "MultiPolygon":
            geom = {
                "type": "MultiPolygon",
                "coordinates": [[simplify_ring(r) for r in poly] for poly in geom["coordinates"]],
            }
        out["features"].append(
            {
                "type": "Feature",
                "properties": {"source": "UNEP-WCMC seagrass v7.1", "id": feat.get("id")},
                "geometry": geom,
            }
        )
    return out


def slim_pts(fc: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "unep-wcmc-seagrass-points-palk",
        "features": [
            {
                "type": "Feature",
                "properties": {"source": "UNEP-WCMC seagrass v7.1 points", "id": f.get("id")},
                "geometry": f["geometry"],
            }
            for f in fc.get("features", [])
        ],
    }


def main() -> None:
    polys = slim_poly(query(1, 50))
    pts = slim_pts(query(0, 100))
    (ROOT / "data" / "seagrass_unep_palk.geojson").write_text(json.dumps(polys), encoding="utf-8")
    (ROOT / "data" / "seagrass_unep_palk_pts.geojson").write_text(json.dumps(pts), encoding="utf-8")
    print(f"wrote {len(polys['features'])} polygons, {len(pts['features'])} points")


if __name__ == "__main__":
    main()
