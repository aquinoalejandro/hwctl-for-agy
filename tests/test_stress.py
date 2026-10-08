"""Unit tests for GPU stress generator and environment health checks."""

import unittest

from hwctl.core.controller import HardwareController
from hwctl.experiments.stress import GpuStressGenerator, ThermalStressExperiment
from hwctl.providers.mock.provider import MockGpuProvider


class TestStress(unittest.TestCase):

    def setUp(self):
        self.controller = HardwareController(provider_name="mock")

    def tearDown(self):
        self.controller.shutdown()

    def test_environment_check(self):
        res = self.controller.check_environment()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("is_admin", data)
        self.assertIn("adl_available", data)
        self.assertIn("opencl_available", data)
        self.assertIn("conflicting_processes", data)

    def test_stress_generator_start_stop(self):
        gen = GpuStressGenerator()
        gen.start(duration_seconds=5.0)
        self.assertTrue(gen.is_running())
        gen.stop()
        self.assertFalse(gen.is_running())

    def test_thermal_stress_experiment_healthy(self):
        mock_gpu = MockGpuProvider(fault_mode="none")
        exp = ThermalStressExperiment(gpu_provider=mock_gpu)
        res = exp.run(duration_seconds=2.0, sample_interval_seconds=1.0)

        self.assertTrue(res.success)
        self.assertFalse(res.aborted_by_safety)
        self.assertGreater(len(res.samples), 0)
        # Healthy fan should ramp under load
        self.assertGreater(res.peak_rpm, 2000)

    def test_thermal_stress_experiment_stuck_fan(self):
        mock_gpu = MockGpuProvider(fault_mode="stuck_fan")
        exp = ThermalStressExperiment(gpu_provider=mock_gpu)
        res = exp.run(duration_seconds=2.0, sample_interval_seconds=1.0)

        self.assertTrue(res.success)
        self.assertEqual(res.peak_rpm, 1127)
        self.assertEqual(res.final_rpm, 1127)

    def test_thermal_stress_emergency_abort(self):
        # Configure tripwire at 60C so it triggers immediately under simulated load
        mock_gpu = MockGpuProvider(fault_mode="stuck_fan")
        exp = ThermalStressExperiment(gpu_provider=mock_gpu)
        res = exp.run(duration_seconds=5.0, sample_interval_seconds=0.5, emergency_temp_c=60.0)

        self.assertTrue(res.aborted_by_safety)
        self.assertIsNotNone(res.abort_reason)
        self.assertIn("CORE_TEMP_TRIP", res.abort_reason)


if __name__ == "__main__":
    unittest.main()
