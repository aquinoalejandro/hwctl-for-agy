"""Unit tests for controlled experiments and simulated diagnostic runs."""

import unittest

from hwctl.experiments.fan_step import FanStepExperiment
from hwctl.providers.mock.provider import MockGpuProvider


class TestExperiments(unittest.TestCase):

    def test_healthy_fan_step_experiment(self):
        mock_gpu = MockGpuProvider(fault_mode="none")
        exp = FanStepExperiment(gpu_provider=mock_gpu)

        result = exp.run(
            steps=[20.0, 50.0, 80.0],
            hold_duration_seconds=1.0,
            sample_interval_seconds=1.0,
            restore_on_finish=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 3)
        self.assertTrue(result.restored_original_state)

        # In healthy mode, higher steps produce higher RPM
        rpm_step1 = result.steps[0].final_sensors.fan.rpm
        rpm_step2 = result.steps[1].final_sensors.fan.rpm
        rpm_step3 = result.steps[2].final_sensors.fan.rpm

        self.assertGreater(rpm_step2, rpm_step1)
        self.assertGreater(rpm_step3, rpm_step2)

    def test_stuck_fan_step_experiment(self):
        # Simulates the specific user problem: RPM fixed regardless of percentage
        mock_gpu = MockGpuProvider(fault_mode="stuck_fan")
        exp = FanStepExperiment(gpu_provider=mock_gpu)

        result = exp.run(
            steps=[25.0, 50.0, 75.0, 100.0],
            hold_duration_seconds=1.0,
            sample_interval_seconds=1.0,
            restore_on_finish=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 4)

        # All steps report exactly 1127 RPM despite different target percentages
        for step in result.steps:
            self.assertEqual(step.final_sensors.fan.rpm, 1127)


if __name__ == "__main__":
    unittest.main()
