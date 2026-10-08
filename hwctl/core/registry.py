import platform
from typing import Dict, List, Optional, Type

from hwctl.core.exceptions import HardwareNotFoundError
from hwctl.providers.amd.linux import AmdLinuxProvider
from hwctl.providers.amd.provider import AmdGpuProvider
from hwctl.providers.base import BaseGpuProvider, BaseSystemProvider
from hwctl.providers.intel.provider import IntelGpuProvider
from hwctl.providers.mock.provider import MockGpuProvider
from hwctl.providers.nvidia.provider import NvidiaGpuProvider
from hwctl.providers.system.linux import LinuxSystemProvider
from hwctl.providers.system.windows import WindowsSystemProvider


class ProviderRegistry:
    """Discovers, instantiates, and caches hardware providers."""

    def __init__(self):
        self._gpu_providers: Dict[str, BaseGpuProvider] = {}
        self._system_provider: Optional[BaseSystemProvider] = None
        self._mock_fault_mode = "none"

    def register_gpu_provider(self, name: str, provider: BaseGpuProvider) -> None:
        self._gpu_providers[name.lower()] = provider

    def set_system_provider(self, provider: BaseSystemProvider) -> None:
        self._system_provider = provider

    def get_system_provider(self) -> BaseSystemProvider:
        if self._system_provider is None:
            if platform.system() == "Linux":
                self._system_provider = LinuxSystemProvider()
            else:
                self._system_provider = WindowsSystemProvider()
        return self._system_provider

    def set_mock_fault_mode(self, fault_mode: str) -> None:
        """Sets fault mode for Mock provider (e.g. 'stuck_fan', 'no_fan_control', 'none')."""
        self._mock_fault_mode = fault_mode
        if "mock" in self._gpu_providers:
            self._gpu_providers["mock"] = MockGpuProvider(fault_mode=fault_mode)

    def _create_amd_provider(self) -> BaseGpuProvider:
        """Creates AMD provider adapted to host OS (sysfs/hwmon on Linux, ADL on Windows)."""
        if platform.system() == "Linux":
            return AmdLinuxProvider()
        return AmdGpuProvider()

    def get_gpu_provider(self, force_provider: Optional[str] = None) -> BaseGpuProvider:
        """Resolves the appropriate GPU provider."""
        if force_provider:
            p_name = force_provider.lower()
            if p_name == "mock":
                if "mock" not in self._gpu_providers:
                    self._gpu_providers["mock"] = MockGpuProvider(fault_mode=self._mock_fault_mode)
                return self._gpu_providers["mock"]
            elif p_name == "amd":
                if "amd" not in self._gpu_providers:
                    self._gpu_providers["amd"] = self._create_amd_provider()
                return self._gpu_providers["amd"]
            elif p_name == "nvidia":
                if "nvidia" not in self._gpu_providers:
                    self._gpu_providers["nvidia"] = NvidiaGpuProvider()
                return self._gpu_providers["nvidia"]
            elif p_name == "intel":
                if "intel" not in self._gpu_providers:
                    self._gpu_providers["intel"] = IntelGpuProvider()
                return self._gpu_providers["intel"]
            else:
                raise HardwareNotFoundError(f"Unknown hardware provider '{force_provider}'.")

        # Auto-detect hardware
        # 1. AMD Check
        if "amd" not in self._gpu_providers:
            amd = self._create_amd_provider()
            if amd.is_available():
                self._gpu_providers["amd"] = amd
                return amd
        elif self._gpu_providers["amd"].is_available():
            return self._gpu_providers["amd"]

        # 2. NVIDIA Check
        if "nvidia" not in self._gpu_providers:
            nv = NvidiaGpuProvider()
            if nv.is_available():
                self._gpu_providers["nvidia"] = nv
                return nv
        elif self._gpu_providers["nvidia"].is_available():
            return self._gpu_providers["nvidia"]

        # 3. Intel Check
        if "intel" not in self._gpu_providers:
            intel = IntelGpuProvider()
            if intel.is_available():
                self._gpu_providers["intel"] = intel
                return intel

        # If nothing detected or running in test/mock environment
        if "mock" not in self._gpu_providers:
            self._gpu_providers["mock"] = MockGpuProvider(fault_mode=self._mock_fault_mode)
        return self._gpu_providers["mock"]
