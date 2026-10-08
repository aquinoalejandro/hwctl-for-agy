"""Unit tests for safety bounds, parameter validation, and rollback mechanism."""

import unittest

from hwctl.core.exceptions import InvalidParameterError, SafetyViolationError
from hwctl.core.safety import RollbackManager, SafetyGuard


class TestSafety(unittest.TestCase):

    def test_valid_fan_percentage(self):
        self.assertEqual(SafetyGuard.validate_fan_percent(0.0), 0.0)
        self.assertEqual(SafetyGuard.validate_fan_percent(50), 50.0)
        self.assertEqual(SafetyGuard.validate_fan_percent(100.0), 100.0)

    def test_invalid_fan_percentage_bounds(self):
        with self.assertRaises(SafetyViolationError):
            SafetyGuard.validate_fan_percent(-0.1)

        with self.assertRaises(SafetyViolationError):
            SafetyGuard.validate_fan_percent(100.1)

        with self.assertRaises(SafetyViolationError):
            SafetyGuard.validate_fan_percent(250)

    def test_invalid_fan_percentage_types(self):
        with self.assertRaises(InvalidParameterError):
            SafetyGuard.validate_fan_percent(None)

        with self.assertRaises(InvalidParameterError):
            SafetyGuard.validate_fan_percent("invalid")

    def test_duration_validation(self):
        self.assertEqual(SafetyGuard.validate_duration(5.0), 5.0)

        with self.assertRaises(InvalidParameterError):
            SafetyGuard.validate_duration(0.5)

        with self.assertRaises(SafetyViolationError):
            SafetyGuard.validate_duration(500.0)

    def test_rollback_manager(self):
        rb = RollbackManager()
        state = {"fan_mode": "auto"}
        restored = {"called": False}

        def mock_restore():
            restored["called"] = True

        rb.capture_state(state, mock_restore)
        self.assertFalse(restored["called"])

        # Execute rollback
        success = rb.execute_rollback()
        self.assertTrue(success)
        self.assertTrue(restored["called"])

        # Second execute rollback should be a no-op as state was cleared
        self.assertFalse(rb.execute_rollback())


if __name__ == "__main__":
    unittest.main()
