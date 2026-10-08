"""Intel GPU Provider (Foundation & Extensible Stub).

Demonstrates modular multi-vendor architecture for Intel Arc / UHD graphics.
"""

from typing import Any, Dict, List, Optional
import winreg

from hwctl.core.exceptions import FanControlUnavailableError, HardwareNotFoundError, UnsupportedFeatureError
from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors
from hwctl.providers.base import BaseGpuProvider


class IntelGpuProvider(BaseGpuProvider):
    """Intel Arc/Iris Xe GPU provider implementation stub."""

    @property
    def vendor_name(self) -> str:
        return "Intel"

    def is_available(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000") as key:
                desc, _ = winreg.QueryValueEx(key, "DriverDesc")
                return "INTEL" in str(desc).upper()
        except OSError:
            return False

    def initialize(self) -> None:
        pass

    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        return GpuInfo(
            adapter_index=adapter_index,
            vendor="Intel",
            model="Intel Graphics Device",
            is_primary=False,
        )

    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        return GpuSensors(fan=FanStatus(control_mode="auto"))

    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        return FanStatus(control_mode="auto")

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        raise FanControlUnavailableError("Intel GPU fan control requires Intel ControlLib / LevelZero module.")

    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        raise UnsupportedFeatureError("manual_fan_control", "Intel fan control is not implemented.")

    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        raise UnsupportedFeatureError("manual_fan_control", "Intel fan control is not implemented.")

    def reset_gpu_fan_control(self, adapter_index: int = 0) -> ActionResult:
        return ActionResult(success=True, action="reset_gpu_fan_control", data={"status": "auto_default"})

    def get_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        return {"vendor": "Intel", "status": "Foundation stub available"}

    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        return {"status": "GOP/VBIOS retrieval pending Intel driver bridge"}

    def shutdown(self) -> None:
        pass
