"""
Unit tests for the NeuroSim-inspired partial-sum ADC quantization overlay.

Covers two layers:

1. ``pim_sim.device.model.PartialSumADCNoiseModel`` — standalone math and
   compositional behaviour (validation errors, sigma formula,
   high-precision limit converges to the inner model).
2. ``mnsim_adapter.overlay._build_device_model`` — opt-in wiring.
   Chips that do not set ``ADCProfile.accuracy_bits`` must produce a bare
   base DeviceModel (regression-safe for existing literature-anchor
   baselines). Chips that do opt in must get the wrapper, but only when
   they are an analog NVM macro (SRAM / digital-PIM must skip it).
"""

from __future__ import annotations

import math
import unittest
import warnings
from dataclasses import replace

import numpy as np

from mnsim_adapter import Provenance, Traced, load_chip
from mnsim_adapter.overlay import _build_device_model
from pim_sim.device.model import (
    AsymmetricGaussianModel,
    PartialSumADCNoiseModel,
    SymmetricGaussianModel,
)


class PartialSumADCNoiseModelTest(unittest.TestCase):
    def _make(self, **overrides):
        defaults = dict(
            inner=SymmetricGaussianModel(variation_pct=0.0),
            adc_bits=5.0,
            subarray_rows=128,
            g_lrs_siemens=1.0 / 6.0e4,
            input_activity=0.5,
        )
        defaults.update(overrides)
        return PartialSumADCNoiseModel(**defaults)

    def test_rejects_adc_bits_below_one(self) -> None:
        with self.assertRaises(ValueError):
            self._make(adc_bits=0.5)

    def test_rejects_zero_rows(self) -> None:
        with self.assertRaises(ValueError):
            self._make(subarray_rows=0)

    def test_rejects_activity_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            self._make(input_activity=0.0)
        with self.assertRaises(ValueError):
            self._make(input_activity=1.5)

    def test_rejects_non_positive_g_lrs(self) -> None:
        with self.assertRaises(ValueError):
            self._make(g_lrs_siemens=0.0)

    def test_sigma_formula_matches_closed_form(self) -> None:
        """σ_G_adc = G_LRS / (sqrt(12·N·a) · 2^B) — verify to 12 sig figs."""
        m = self._make(
            adc_bits=5.0,
            subarray_rows=128,
            g_lrs_siemens=1.0 / 6.0e4,
            input_activity=0.5,
        )
        expected = (1.0 / 6.0e4) / (math.sqrt(12.0 * 128.0 * 0.5) * 2.0 ** 5)
        self.assertAlmostEqual(m.sigma_g_adc_equivalent(), expected, places=15)

    def test_sigma_decays_with_bits(self) -> None:
        """Each extra ADC bit halves σ_G_adc (levels double)."""
        low = self._make(adc_bits=4.0)
        high = self._make(adc_bits=5.0)
        self.assertAlmostEqual(
            high.sigma_g_adc_equivalent() * 2.0,
            low.sigma_g_adc_equivalent(),
            places=15,
        )

    def test_high_bits_converges_to_inner(self) -> None:
        """With very many ADC bits the added noise is ~0; samples match inner."""
        inner = SymmetricGaussianModel(variation_pct=0.0)
        model = self._make(inner=inner, adc_bits=24.0)
        rng = np.random.default_rng(0)
        samples = model.sample_resistance(
            nominal_resistance=1.0e5,
            state_index=0,
            shape=(1024,),
            rng=rng,
        )
        # Noise floor well below 0.1% of nominal R.
        self.assertLess(float(np.std(samples)) / 1.0e5, 1e-3)

    def test_low_bits_produces_measurable_noise(self) -> None:
        """At B=4 with N=128, a=0.5 the per-cell σ_R is order-of-magnitude
        comparable to the MNSIM 1% baseline — confirm it's nonzero and finite."""
        inner = SymmetricGaussianModel(variation_pct=0.0)
        model = self._make(inner=inner, adc_bits=4.0)
        rng = np.random.default_rng(1)
        samples = model.sample_resistance(
            nominal_resistance=6.0e4,
            state_index=1,
            shape=(4096,),
            rng=rng,
        )
        std_rel = float(np.std(samples)) / 6.0e4
        self.assertGreater(std_rel, 0.0)
        self.assertTrue(math.isfinite(std_rel))

    def test_samples_stay_strictly_positive(self) -> None:
        """Conductance floor guarantees the reciprocal never blows up."""
        model = self._make(adc_bits=1.0, subarray_rows=1, input_activity=1.0)
        rng = np.random.default_rng(2)
        samples = model.sample_resistance(
            nominal_resistance=6.0e4,
            state_index=1,
            shape=(1024,),
            rng=rng,
        )
        self.assertTrue(bool(np.all(samples > 0)))
        self.assertTrue(bool(np.all(np.isfinite(samples))))

    def test_summary_shape(self) -> None:
        s = self._make().summary()
        self.assertEqual(s["model"], "partial_sum_adc_noise")
        self.assertIn("inner", s)
        self.assertIn("sigma_g_adc_siemens", s)


class OverlayOptOutTest(unittest.TestCase):
    """Default literature-anchor chips must NOT engage the wrapper.

    This is the regression guard for the existing
    ``validate/literature_anchor_baseline.py`` outputs. If it ever fails,
    pim_sim's baseline numbers would shift silently.
    """

    def test_liu_default_has_no_partial_sum_wrapper(self) -> None:
        chip = load_chip("rram_isscc2020_33p2")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = _build_device_model(chip)
        self.assertIsInstance(model, SymmetricGaussianModel)
        self.assertNotIsInstance(model, PartialSumADCNoiseModel)

    def test_yan_sram_has_no_device_model_even_if_accuracy_bits_set(self) -> None:
        """SRAM path returns None regardless of accuracy_bits (NVM guard)."""
        chip = load_chip("sram_isscc2022_11p7")
        accuracy_bits = Traced(4, Provenance(kind="design", source="test"))
        patched_adc = replace(chip.circuit.adc, accuracy_bits=accuracy_bits)
        patched_circuit = chip.circuit.with_adc(patched_adc)
        patched = replace(chip, circuit=patched_circuit)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = _build_device_model(patched)
        self.assertIsNone(model)


class OverlayOptInTest(unittest.TestCase):
    """Opting Liu in via ``ADCProfile.accuracy_bits`` wraps with the model."""

    def _patch_liu_with_accuracy_bits(self, bits: int):
        chip = load_chip("rram_isscc2020_33p2")
        accuracy_bits = Traced(bits, Provenance(kind="design", source="test"))
        patched_adc = replace(chip.circuit.adc, accuracy_bits=accuracy_bits)
        patched_circuit = chip.circuit.with_adc(patched_adc)
        return replace(chip, circuit=patched_circuit)

    def test_accuracy_bits_wraps_with_partial_sum_model(self) -> None:
        chip = self._patch_liu_with_accuracy_bits(5)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = _build_device_model(chip)
        self.assertIsInstance(model, PartialSumADCNoiseModel)
        self.assertEqual(float(model.adc_bits), 5.0)
        # Inner must be a proper DeviceModel, not None.
        self.assertIsInstance(
            model.inner,
            (SymmetricGaussianModel, AsymmetricGaussianModel),
        )
        # Subarray rows come from the architecture.xbar.rows field (784).
        self.assertEqual(int(model.subarray_rows), 784)
        # g_lrs derived from 1 / 6e4.
        self.assertAlmostEqual(
            model.g_lrs_siemens,
            1.0 / 6.0e4,
            places=12,
        )

    def test_explicit_input_activity_propagates(self) -> None:
        chip = self._patch_liu_with_accuracy_bits(4)
        activity = Traced(0.25, Provenance(kind="design", source="test"))
        patched_adc = replace(chip.circuit.adc, accuracy_input_activity=activity)
        patched_circuit = chip.circuit.with_adc(patched_adc)
        patched = replace(chip, circuit=patched_circuit)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = _build_device_model(patched)
        self.assertIsInstance(model, PartialSumADCNoiseModel)
        self.assertAlmostEqual(model.input_activity, 0.25, places=12)


if __name__ == "__main__":
    unittest.main()
