import configparser as cp
import os
import unittest
from pathlib import Path

from dse.core import write_temp_config


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = REPO_ROOT / "configs" / "SimConfig.ini"


class MeasuredScenarioPatchTest(unittest.TestCase):
    def test_post_patch_preserves_measured_device_fields_after_rram_preset(self) -> None:
        cfg = {
            "rram_preset": "P0",
            "xbar_size": (128, 128),
            "adc_choice": 4,
            "dac_num": 32,
            "xbar_polarity": 2,
            "sub_position": 1,
            "group_num": 1,
            "pe_num": (2, 2),
            "tile_connection": 2,
            "inter_tile_bw": 80,
        }
        measured_patch = {
            "Device level": {
                "Device_Resistance": "14261.58,2325.34",
                "Device_Variation": "16.670",
                "Device_SAF": "0.1179,0.1179",
            }
        }

        temp_path = write_temp_config(str(BASE_CONFIG), cfg, post_patch=measured_patch)
        try:
            parser = cp.ConfigParser()
            parser.read(temp_path, encoding="UTF-8")
            self.assertEqual(parser.get("Device level", "Device_Resistance"), "14261.58,2325.34")
            self.assertEqual(parser.get("Device level", "Device_Variation"), "16.670")
            self.assertEqual(parser.get("Device level", "Device_SAF"), "0.1179,0.1179")
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
