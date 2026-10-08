"""Unit tests for the central HardwareController."""

import unittest

from hwctl.core.controller import HardwareController


class TestController(unittest.TestCase):

    def setUp(self):
        self.controller = HardwareController(provider_name="mock")

    def tearDown(self):
        self.controller.shutdown()

    def test_get_system_info(self):
        res = self.controller.get_system_info()
        self.assertTrue(res["success"])
        self.assertIn("cpu_model", res["data"])
        self.assertIn("ram_total_mb", res["data"])

    def test_get_gpu_info(self):
        res = self.controller.get_gpu_info()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["vendor"], "AMD")
        self.assertEqual(res["data"]["vram_mb"], 8192)

    def test_get_gpu_sensors(self):
        res = self.controller.get_gpu_sensors()
        self.assertTrue(res["success"])
        self.assertIn("temperature_c", res["data"])
        self.assertIn("fan", res["data"])

    def test_set_gpu_fan_percent_valid(self):
        res = self.controller.set_gpu_fan_percent(65.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["requested_percent"], 65.0)
        self.assertEqual(res["reported_percent"], 65.0)

    def test_set_gpu_fan_percent_safety_violation(self):
        res = self.controller.set_gpu_fan_percent(150.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SAFETY_VIOLATION")

    def test_reset_gpu_fan_control(self):
        res = self.controller.reset_gpu_fan_control()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["control_mode"], "auto")

    def test_create_diagnostic_snapshot(self):
        res = self.controller.create_diagnostic_snapshot()
        self.assertTrue(res["success"])
        self.assertIn("system", res["data"])
        self.assertIn("gpu", res["data"])
        self.assertIn("sensors", res["data"])


if __name__ == "__main__":
    unittest.main()
