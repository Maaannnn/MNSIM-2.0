"""
Tests for the named ADC preset library.

Covers:

1. Registry coverage (all seed rows load, unique preset_ids).
2. Acceptance criterion #2 from docs/simulator/pluggable_adc_library.md:
   ``REGISTRY["sar_modern"].fom_walden_j_per_conv == 20.36e-15`` (within
   rounding).
3. ``.to_model()`` carries the preset's FoMs into WaldenADCModel.
4. Bit-identical parity with the seed CSV — guards against drift between
   the embedded table and ``validate/walden_murmann_validation.py``.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from pim_sim.array.adc_library import (
    ADCPreset,
    REGISTRY,
    get_preset,
)
from pim_sim.array.adc_model import WaldenADCModel


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CSV = REPO_ROOT / "validate/output/walden_murmann/adc_preset_library_seed.csv"


class ADCPresetRegistryTest(unittest.TestCase):
    def test_registry_non_empty(self) -> None:
        self.assertGreaterEqual(len(REGISTRY), 14)

    def test_preset_ids_unique(self) -> None:
        self.assertEqual(len(set(REGISTRY)), len(REGISTRY))

    def test_sar_modern_matches_acceptance_criterion(self) -> None:
        # Design memo §5 criterion #2: silicon median for SAR modern subset
        # must round to 20.36 fJ/conv-step.
        preset = REGISTRY["sar_modern"]
        self.assertAlmostEqual(
            preset.fom_walden_j_per_conv * 1e15, 20.36, places=2
        )
        self.assertEqual(preset.architecture, "SAR")
        self.assertEqual(preset.era, "modern")

    def test_get_preset_raises_on_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_preset("does_not_exist")

    def test_all_presets_have_positive_foms_and_provenance(self) -> None:
        for preset_id, preset in REGISTRY.items():
            self.assertIsInstance(preset, ADCPreset)
            self.assertGreater(preset.fom_walden_j_per_conv, 0.0, preset_id)
            self.assertGreater(preset.fom_area_um2, 0.0, preset_id)
            self.assertGreaterEqual(preset.n_silicon_points, 8, preset_id)
            self.assertIn(preset.era, {"legacy", "modern"}, preset_id)


class ADCPresetToModelTest(unittest.TestCase):
    def test_to_model_carries_fom_values(self) -> None:
        preset = REGISTRY["sar_modern"]
        model = preset.to_model(enob=6.0, sample_rate_gsps=1.0)
        self.assertIsInstance(model, WaldenADCModel)
        self.assertEqual(model.fom_walden_j_per_conv, preset.fom_walden_j_per_conv)
        self.assertEqual(model.fom_area_um2, preset.fom_area_um2)
        self.assertEqual(model.enob, 6.0)
        self.assertEqual(model.sample_rate_gsps, 1.0)

    def test_to_model_power_uses_preset_fom(self) -> None:
        # At ENOB=6, fs=1 GSa/s: P = FoM_W * 2^6 * 1e9 = FoM_W * 6.4e10.
        preset = REGISTRY["sar_modern"]
        expected_w = preset.fom_walden_j_per_conv * (2.0 ** 6) * 1e9
        self.assertAlmostEqual(preset.to_model(6.0, 1.0).power_w(), expected_w)


class ADCPresetSeedParityTest(unittest.TestCase):
    """Embedded FoMs must match the seed CSV bit-identically."""

    def test_parity_with_seed_csv(self) -> None:
        self.assertTrue(
            SEED_CSV.exists(),
            f"Seed CSV missing: {SEED_CSV}. "
            "Run validate/walden_murmann_validation.py to regenerate.",
        )
        with SEED_CSV.open() as f:
            rows = list(csv.DictReader(f))

        matched = 0
        for row in rows:
            arch = row["architecture"]
            era = row["era"]
            from pim_sim.array.adc_library import _normalize_arch  # internal helper
            preset_id = f"{_normalize_arch(arch)}_{era}"
            self.assertIn(preset_id, REGISTRY, f"Missing preset for CSV row {arch}/{era}")
            preset = REGISTRY[preset_id]
            self.assertAlmostEqual(
                preset.fom_walden_j_per_conv * 1e15,
                float(row["fomw_fj_median"]),
                places=9,
                msg=f"FoM_W drift on {preset_id}",
            )
            self.assertAlmostEqual(
                preset.fom_area_um2,
                float(row["foma_um2_median"]),
                places=9,
                msg=f"FoM_A drift on {preset_id}",
            )
            matched += 1
        self.assertEqual(matched, len(REGISTRY))


if __name__ == "__main__":
    unittest.main()
