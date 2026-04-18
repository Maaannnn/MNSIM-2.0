import configparser as cp
import unittest
from pathlib import Path

from app.backend.shared import derive_effective_config
from app.backend.validity import annotate_artifact


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = REPO_ROOT / "configs" / "SimConfig.ini"


class ArtifactValidityTest(unittest.TestCase):
    def test_known_historical_measured_run_is_invalidated(self) -> None:
        annotated = annotate_artifact(
            "matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/matrixcsv_seed42",
            status="completed",
        )
        self.assertTrue(annotated["is_invalidated"])
        self.assertEqual(annotated["status"], "invalidated")
        self.assertIn("nominal preset", annotated["invalidation"]["reason"])

    def test_unrelated_run_is_not_invalidated(self) -> None:
        annotated = annotate_artifact(
            "matrix_runs/ws2_a_full_20260417_202402",
            status="completed",
        )
        self.assertFalse(annotated["is_invalidated"])
        self.assertEqual(annotated["status"], "completed")


class EffectiveConfigScenarioPatchTest(unittest.TestCase):
    def test_scenario_patch_is_reapplied_after_rram_preset(self) -> None:
        params = {
            "rram_preset": "P0",
            "xbar_size": "128x128",
            "adc_choice": 4,
            "dac_num": 32,
            "xbar_polarity": 2,
            "sub_position": 1,
            "group_num": 1,
            "pe_num": "2x2",
            "tile_connection": 2,
            "inter_tile_bw": 80,
        }
        scenario_patch = {
            "Device level": {
                "Device_Resistance": "14261.58,2325.34",
                "Device_Variation": "16.670",
                "Device_SAF": "0.1179,0.1179",
            }
        }

        effective = derive_effective_config(
            BASE_CONFIG.read_text(encoding="utf-8"),
            params,
            scenario_patch=scenario_patch,
        )
        parser = cp.ConfigParser()
        parser.optionxform = str
        parser.read_string(effective["content"])

        self.assertEqual(parser.get("Device level", "Device_Resistance"), "14261.58,2325.34")
        self.assertEqual(parser.get("Device level", "Device_Variation"), "16.670")
        self.assertEqual(parser.get("Device level", "Device_SAF"), "0.1179,0.1179")
        self.assertTrue(any(item["source"] == "scenario_post_patch" for item in effective["overrides"]))


if __name__ == "__main__":
    unittest.main()
