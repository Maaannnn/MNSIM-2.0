"""
Unit tests for the ChipProfile.variation → pim_sim.DeviceModel factory.

The factory ``pim_sim.device.factory.device_model_from_variation`` is the
single source of truth for "which pim_sim DeviceModel backs a given
VariationModel". It is also the hot path through which fab-measured
wafer CVs become runtime accuracy models, so regressions here would
silently change every pim_sim accuracy number.
"""

from __future__ import annotations

import unittest

import warnings

from mnsim_adapter import (
    AsymmetricVariation,
    Provenance,
    ProvenanceWarning,
    SymmetricVariation,
    collect_weak_fields,
    load_chip,
    warn_weak_fields,
)
from pim_sim import device_model_from_variation
from pim_sim.device.model import (
    AsymmetricGaussianModel,
    SymmetricGaussianModel,
)


class VariationFactoryTest(unittest.TestCase):
    def test_none_falls_through(self) -> None:
        """None must return None so pim_sim_weight_inject falls back to MNSIM."""
        self.assertIsNone(device_model_from_variation(None))

    def test_symmetric_variation_maps_to_symmetric_model(self) -> None:
        v = SymmetricVariation(
            kind="symmetric_gaussian",
            cv_pct=2.5,
            provenance=Provenance(kind="empirical", source="fab report X"),
        )
        m = device_model_from_variation(v)
        self.assertIsInstance(m, SymmetricGaussianModel)
        self.assertEqual(m.variation_pct, 2.5)

    def test_asymmetric_variation_maps_to_asymmetric_model(self) -> None:
        v = AsymmetricVariation(
            kind="asymmetric_gaussian",
            state_cv_pct=(25.0, 13.0),
            provenance=Provenance(kind="empirical", source="wafer_xy16-25"),
        )
        m = device_model_from_variation(v)
        self.assertIsInstance(m, AsymmetricGaussianModel)
        self.assertEqual(m.state_cv_pct, [25.0, 13.0])

    def test_asymmetric_with_mlc_states(self) -> None:
        """Multi-level cells need per-state CVs beyond HRS/LRS."""
        v = AsymmetricVariation(
            kind="asymmetric_gaussian",
            state_cv_pct=(30.0, 20.0, 15.0, 10.0),
            provenance=Provenance(kind="empirical", source="4-level MLC"),
        )
        m = device_model_from_variation(v)
        self.assertIsInstance(m, AsymmetricGaussianModel)
        self.assertEqual(m.state_cv_pct, [30.0, 20.0, 15.0, 10.0])


class ChipProfileOverlayTest(unittest.TestCase):
    """Verify the full ChipProfile.to_pim_sim_overlay() path on registered chips."""

    def test_liu_isscc2020_33p2_overlay_has_symmetric_model(self) -> None:
        chip = load_chip("rram_isscc2020_33p2")
        overlay = chip.to_pim_sim_overlay()
        self.assertIsInstance(overlay["pim_sim_model"], SymmetricGaussianModel)
        # MNSIM default 1% (proxy) — see mnsim_adapter/registry.py _liu_device().
        self.assertEqual(overlay["pim_sim_model"].variation_pct, 1.0)
        self.assertEqual(overlay["chip_profile_id"], "rram_isscc2020_33p2")

    def test_sram_isscc2022_11p7_overlay_has_no_device_model(self) -> None:
        """SRAM has no variation model; overlay must return None there."""
        chip = load_chip("sram_isscc2022_11p7")
        overlay = chip.to_pim_sim_overlay()
        self.assertIsNone(overlay["pim_sim_model"])
        # pim_sim RRAM-specific overlays are all N/A for SRAM by construction.
        self.assertIsNone(overlay["ir_drop_model"])


class ProvenanceCheckTest(unittest.TestCase):
    """Verify Tier-1/Tier-2 proxy/missing detection on the registered chips."""

    def test_liu_chip_flags_three_expected_weak_fields(self) -> None:
        chip = load_chip("rram_isscc2020_33p2")
        weak = collect_weak_fields(chip)
        paths = {w.path for w in weak}
        # cell_type (1T1R proxy for paper's SW-2T2R), read_latency_ns
        # (calibrated placeholder), variation (MNSIM default 1%).
        self.assertEqual(
            paths,
            {"device.cell_type", "device.read_latency_ns", "device.variation"},
        )
        # All three are intentional literature-anchor proxies, not missing.
        self.assertTrue(all(w.kind == "proxy" for w in weak))

    def test_yan_chip_flags_only_sram_resistance(self) -> None:
        """Yan SRAM: variation=None is legitimate, not weak; resistance is proxy."""
        chip = load_chip("sram_isscc2022_11p7")
        weak = collect_weak_fields(chip)
        paths = {w.path for w in weak}
        self.assertEqual(paths, {"device.resistance"})

    def test_mnsim_fit_variant_drops_fitted_read_latency(self) -> None:
        """The fit variant re-tags read_latency_ns as 'fitted', so it must not
        appear in the weak-fields list any more — only cell_type and variation."""
        chip = load_chip("rram_isscc2020_33p2_mnsim_fit")
        paths = {w.path for w in collect_weak_fields(chip)}
        self.assertEqual(paths, {"device.cell_type", "device.variation"})

    def test_warn_emits_provenance_warning_on_liu(self) -> None:
        chip = load_chip("rram_isscc2020_33p2")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            weak = warn_weak_fields(chip)
        self.assertEqual(len(weak), 3)
        prov_warnings = [w for w in caught if issubclass(w.category, ProvenanceWarning)]
        self.assertEqual(len(prov_warnings), 1)
        self.assertIn("rram_isscc2020_33p2", str(prov_warnings[0].message))
        self.assertIn("device.variation", str(prov_warnings[0].message))

    def test_build_overlay_emits_warning(self) -> None:
        """overlay.build_overlay() must emit the same warning during any
        pim_sim overlay construction, so validation scripts surface it."""
        chip = load_chip("rram_isscc2020_33p2")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            chip.to_pim_sim_overlay()
        prov_warnings = [w for w in caught if issubclass(w.category, ProvenanceWarning)]
        self.assertEqual(len(prov_warnings), 1)


if __name__ == "__main__":
    unittest.main()
