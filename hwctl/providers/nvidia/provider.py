"""NVIDIA GPU Provider (Foundation & Extensible Stub).

Demonstrates modular multi-vendor architecture. Can interface with NVAPI or NVML.
"""

from typing import Any, Dict, List, Optional
import winreg

from hwctl.core.exceptions import FanControlUnavailableError, HardwareNotFoundError, UnsupportedFeatureError
from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors
from hwctl.providers.base import BaseGpuProvider


class NvidiaGpuProvider(BaseGpuProvider):
    """NVIDIA provider implementation stub."""

    @property
    def vendor_name(self) -> str:
        return "NVIDIA"

    def is_available(self) -> bool:
        # Check if NVAPI or an NVIDIA adapter exists in Windows Registry
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000") as key:
                desc, _ = winreg.QueryValueEx(key, "DriverDesc")
                return "NVIDIA" in str(desc).upper()
        except OSError:
            return False

    def initialize(self) -> None:
        pass

    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        # Retrieve basic info from Registry/WMI for NVIDIA adapters
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000") as key:
                desc, _ = winreg.QueryValueEx(key, "DriverDesc")
                driver_ver, _ = winreg.QueryValueEx(key, "DriverVersion")
                return GpuInfo(
                    adapter_index=adapter_index,
                    vendor="NVIDIA",
                    model=str(desc),
                    driver_version=str(driver_ver),
                    is_primary=True,
                )
        except OSError:
            return GpuInfo(
                adapter_index=adapter_index,
                vendor="NVIDIA",
                model="NVIDIA GPU",
                is_primary=True,
            )

    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        # In this stub stage, inform caller that real-time NVAPI telemetry is pending NVAPI/NVML integration
        return GpuSensors(
            fan=FanStatus(control_mode="auto"),
        )

    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        return FanStatus(control_mode="auto")

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        raise FanControlUnavailableError(
            "NVIDIA fan control requires NVAPI (NvAPI_GPU_SetCoolerLevels) integration which is not yet enabled."
        )

    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        raise UnsupportedFeatureError("manual_fan_control", "NVIDIA manual fan mode requires NVAPI module.")

    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        raise UnsupportedFeatureError("manual_fan_control", "NVIDIA manual fan mode requires NVAPI module.")

    def reset_gpu_fan_control(self, adapter_index: int = 0) -> ActionResult:
        return ActionResult(
            success=True,
            action="reset_gpu_fan_control",
            data={"status": "auto_default"},
        )

    def get_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        info = self.get_gpu_info(adapter_index)
        return {
            "vendor": "NVIDIA",
            "driver_version": info.driver_version,
            "status": "Foundation stub available",
        }

    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        return {"status": "VBIOS retrieval via NVAPI pending"}

    def shutdown(self) -> None:
        pass
