"""Abstract base interfaces for hardware providers.

Enables multi-vendor extensibility (AMD, NVIDIA, Intel, and virtual Mock for tests).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors, ProcessInfo, SystemInfo


class BaseGpuProvider(ABC):
    """Abstract interface defining the contract for vendor-specific GPU implementations."""

    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Name of the vendor (e.g. 'AMD', 'NVIDIA', 'Intel', 'MOCK')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the underlying driver/DLL and compatible hardware are present."""
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Initializes the low-level driver interface/library."""
        pass

    @abstractmethod
    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        """Fetches static identification, driver, and capability data."""
        pass

    @abstractmethod
    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        """Reads real-time telemetry (temperatures, clocks, fan metrics, power)."""
        pass

    @abstractmethod
    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        """Queries the current fan telemetry and control mode."""
        pass

    @abstractmethod
    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        """Sets the fan speed percentage (0 - 100%)."""
        pass

    @abstractmethod
    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        """Switches the fan controller from automatic curve to manual mode."""
        pass

    @abstractmethod
    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        """Switches the fan controller back to automatic driver/VBIOS curve."""
        pass

    @abstractmethod
    def reset_gpu_fan_control(self, adapter_index: int = 0) -> ActionResult:
        """Failsafe method that restores standard automatic control."""
        pass

    @abstractmethod
    def get_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Returns detailed driver version and metadata."""
        pass

    @abstractmethod
    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Safely queries VBIOS/firmware version and serial data if accessible."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Cleans up low-level library handles and restores safe state."""
        pass

    def list_adapters(self) -> List[Dict[str, Any]]:
        """Returns summary info for every detected GPU adapter on this vendor.
        Default implementation returns a single-adapter list from get_gpu_info()."""
        try:
            info = self.get_gpu_info(0)
            return [info.to_dict()]
        except Exception:
            return []

    def get_power_states(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries current and available performance levels / clock-power states.
        Returns best-effort data; not all drivers expose full P-state tables."""
        return {"current_performance_level": "unknown", "states": [], "note": "Not supported by this provider."}

    def get_display_outputs(self, adapter_index: int = 0) -> List[Dict[str, Any]]:
        """Enumerates connected display outputs (monitors, HDMI, DP, etc.).
        Default returns empty list if provider does not implement."""
        return []


class BaseSystemProvider(ABC):
    """Abstract interface for host OS, CPU, RAM, and process telemetry."""

    @abstractmethod
    def get_system_info(self) -> SystemInfo:
        """Queries host OS, CPU, memory, and motherboard overview."""
        pass

    @abstractmethod
    def get_relevant_processes(self) -> List[ProcessInfo]:
        """Identifies active processes that may conflict with GPU control or cause heavy load."""
        pass

    def get_event_logs(self, source_filter: str = "Display", max_entries: int = 30) -> List[Dict[str, Any]]:
        """Reads OS event logs filtered by source (e.g. 'Display', 'nvlddmkm', 'amdgpu').
        Default implementation returns empty list."""
        return []
