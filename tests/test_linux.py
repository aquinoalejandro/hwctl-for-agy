"""Unit tests for Linux/Arch Linux providers and environment detection."""

import unittest

from hwctl.core.controller import HardwareController
from hwctl.providers.amd.linux import AmdLinuxProvider
from hwctl.providers.system.linux import LinuxSystemProvider


class TestLinuxProviders(unittest.TestCase):

    def test_linux_system_provider_instantiation(self):
        provider = LinuxSystemProvider()
        # Even if run on Windows or CI, it should return graceful defaults without raising unhandled errors
        info = provider.get_system_info()
        self.assertIsNotNone(info.os_name)
        self.assertIsNotNone(info.cpu_model)
        self.assertGreater(info.ram_total_mb, 0)

    def test_amd_linux_provider_availability(self):
        provider = AmdLinuxProvider()
        # On non-Linux or when /sys/class/drm is absent, is_available should return False cleanly
        avail = provider.is_available()
        self.assertIsInstance(avail, bool)

    def test_controller_check_environment(self):
        controller = HardwareController(provider_name="mock")
        env = controller.check_environment()
        self.assertTrue(env["success"])
        self.assertIn("active_gpu_vendor", env["data"])
        self.assertIn("notes", env["data"])
        controller.shutdown()


if __name__ == "__main__":
    unittest.main()
