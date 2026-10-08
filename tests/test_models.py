"""Unit tests for data models and schemas."""

import json
import unittest

from hwctl.core.models import (
    ActionResult,
    FanStatus,
    GpuInfo,
    GpuSensors,
    ProcessInfo,
    SystemInfo,
)


class TestModels(unittest.TestCase):

    def test_fan_status_serialization(self):
        fan = FanStatus(
            target_percent=50.0,
            current_percent=50.0,
            rpm=1800,
            control_mode="manual",
            min_percent=0.0,
            max_percent=100.0,
        )
        d = fan.to_dict()
        self.assertEqual(d["target_percent"], 50.0)
        self.assertEqual(d["rpm"], 1800)
        self.assertEqual(d["control_mode"], "manual")
        # Ensure it is valid JSON
        serialized = json.dumps(d)
        self.assertIn('"rpm": 1800', serialized)

    def test_gpu_sensors_serialization(self):
        sensors = GpuSensors(
            temperature_c=75.5,
            hotspot_c=90.2,
            usage_percent=98.0,
            power_w=145.0,
            fan=FanStatus(target_percent=100.0, current_percent=100.0, rpm=2800),
        )
        d = sensors.to_dict()
        self.assertEqual(d["temperature_c"], 75.5)
        self.assertEqual(d["hotspot_c"], 90.2)
        self.assertEqual(d["fan"]["rpm"], 2800)
        self.assertIn("timestamp", d)

    def test_action_result_success_and_error(self):
        success_res = ActionResult(
            success=True,
            action="set_gpu_fan_percent",
            requested_percent=80.0,
            reported_percent=80.0,
            reported_rpm=2400,
            temperature_c=68.0,
        )
        s_dict = success_res.to_dict()
        self.assertTrue(s_dict["success"])
        self.assertEqual(s_dict["requested_percent"], 80.0)

        err_res = ActionResult(
            success=False,
            action="set_gpu_fan_percent",
            error={"code": "FAN_CONTROL_UNAVAILABLE", "message": "Test error"},
        )
        e_dict = err_res.to_dict()
        self.assertFalse(e_dict["success"])
        self.assertEqual(e_dict["error"]["code"], "FAN_CONTROL_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
