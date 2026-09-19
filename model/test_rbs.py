import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rbs import depletion_per_pass, predict


class RbsModelTests(unittest.TestCase):
    def test_tickler_chains_raise_depletion(self):
        base = depletion_per_pass("otter", "seagrass", {})
        bad = depletion_per_pass("otter", "seagrass", {"tickler_chains": True})
        self.assertGreater(bad, base)

    def test_seagrass_collapses_under_heavy_inappropriate_trawl(self):
        pred = predict(
            {
                "gear": "otter_heavy",
                "habitat": "seagrass",
                "sweeps_per_year": 6.4,
                "status0": 0.55,
                "years": 10,
                "practices": {
                    "tickler_chains": True,
                    "too_shallow_on_bed": True,
                    "repeat_same_tracks": True,
                    "spawn_season_tows": True,
                },
            }
        )
        self.assertTrue(pred["chronic"])
        self.assertLess(pred["rbs_horizon"], 0.25)
        self.assertIsNotNone(pred["years_to_collapse"])

    def test_bedsafe_recovers_seagrass(self):
        pred = predict(
            {
                "gear": "otter_heavy",
                "habitat": "seagrass",
                "sweeps_per_year": 6.4,
                "status0": 0.28,
                "years": 10,
                "practices": {"tickler_chains": True, "too_shallow_on_bed": True},
            }
        )
        self.assertGreater(pred["rbs_bedsafe"], pred["rbs_horizon"])
        self.assertGreater(pred["rbs_bedsafe"], 0.7)

    def test_mud_recovers_faster_than_seagrass(self):
        shared = {
            "gear": "otter",
            "sweeps_per_year": 2.0,
            "status0": 0.5,
            "years": 10,
            "practices": {},
        }
        mud = predict({**shared, "habitat": "mud"})
        grass = predict({**shared, "habitat": "seagrass"})
        self.assertGreater(mud["rbs_horizon"], grass["rbs_horizon"])


if __name__ == "__main__":
    unittest.main()
