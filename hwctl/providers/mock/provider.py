"""Mock GPU provider simulating an AMD Radeon RX 580.

Supports realistic telemetry emulation and simulated fault conditions
(such as fans locked at fixed RPM) for rigorous testing and development.
"""

from typing import Any, Dict, Optional

from hwctl.core.exceptions import FanControlUnavailableError
from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors
from hwctl.core.safety import SafetyGuard
from hwctl.providers.base import BaseGpuProvider


class MockGpuProvider(BaseGpuProvider):
    """Simulates an AMD Radeon RX 580 8GB GPU."""

    def __init__(self, fault_mode: str = "none"):
        """
        Args:
            fault_mode:
                - "none": Normal, healthy behavior.
                - "stuck_fan": Simulates stuck fan RPM at ~1127 RPM regardless of percentage target.
                - "no_fan_control": Simulates driver or hardware refusing write access.
        """
        self.fault_mode = fault_mode
        self._target_fan_percent = 40.0
        self._fan_mode = "auto"
        self._base_temp = 55.0
        self._base_hotspot = 68.0
        self._usage_percent = 15.0
        self._power_w = 42.0
        self._under_load = False

    def set_simulated_load(self, active: bool) -> None:
        """Enables or disables simulated stress/load condition."""
        self._under_load = active
        if active:
            self._usage_percent = 99.0
            self._power_w = 148.0
            self._base_temp = 84.0
            self._base_hotspot = 98.0
            if self.fault_mode == "stuck_fan":
                # With stuck fan under load, thermal buildup is worse
                self._base_temp = 88.0
                self._base_hotspot = 104.0
        else:
            self._usage_percent = 15.0
            self._power_w = 42.0
            self._base_temp = 55.0
            self._base_hotspot = 68.0

    @property
    def vendor_name(self) -> str:
        return "AMD"

    def is_available(self) -> bool:
        return True

    def initialize(self) -> None:
        pass

    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        return GpuInfo(
            adapter_index=adapter_index,
            vendor="AMD",
            model="Radeon RX 580 Series (Simulated)",
            sub_vendor="Sapphire Technology Limited",
            vram_mb=8192,
            driver_version="31.0.21912.14 (Adrenalin 23.11.1)",
            vbios_version="113-1E3660U-O51",
            power_limit_w=185.0,
            thermal_limit_c=85.0,
            is_primary=True,
        )

    def _calculate_rpm(self, percent: float) -> int:
        if self.fault_mode == "stuck_fan":
            # Real-world anomaly: Tachometer reports a fixed RPM around 1127
            return 1127

        # Normal response: 0% = 0 RPM (Zero RPM mode), max 3200 RPM
        if percent <= 0.0:
            return 0
        min_spin_rpm = 800
        max_spin_rpm = 3200
        return int(min_spin_rpm + (percent / 100.0) * (max_spin_rpm - min_spin_rpm))

    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        effective_pct = self._target_fan_percent
        if self._under_load and self._fan_mode == "auto":
            # Auto fan curve targets 85% when GPU is under heavy load
            effective_pct = 85.0

        rpm = self._calculate_rpm(effective_pct)
        # Higher fan slightly cools down simulated temp
        effective_temp = max(38.0, self._base_temp - (effective_pct * 0.15))
        effective_hotspot = max(45.0, self._base_hotspot - (effective_pct * 0.18))

        fan = FanStatus(
            target_percent=effective_pct,
            current_percent=effective_pct,
            rpm=rpm,
            control_mode=self._fan_mode,
            min_percent=0.0,
            max_percent=100.0,
            min_rpm=0,
            max_rpm=3200,
        )

        return GpuSensors(
            temperature_c=round(effective_temp, 1),
            hotspot_c=round(effective_hotspot, 1),
            usage_percent=self._usage_percent,
            vram_usage_percent=22.5,
            vram_used_mb=1843.0,
            power_w=self._power_w,
            core_clock_mhz=1340.0,
            memory_clock_mhz=2000.0,
            voltage_mv=1150.0,
            fan=fan,
        )

    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        sensors = self.get_gpu_sensors(adapter_index)
        return sensors.fan

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        if self.fault_mode == "no_fan_control":
            raise FanControlUnavailableError("Hardware or driver rejected fan write command.")

        validated = SafetyGuard.validate_fan_percent(percent)
        self._target_fan_percent = validated
        self._fan_mode = "manual"

        sensors = self.get_gpu_sensors(adapter_index)
        return ActionResult(
            success=True,
            action="set_gpu_fan_percent",
            requested_percent=validated,
            reported_percent=sensors.fan.current_percent,
            reported_rpm=sensors.fan.rpm,
            temperature_c=sensors.temperature_c,
            hotspot_c=sensors.hotspot_c,
            power_w=sensors.power_w,
        )

    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        self._fan_mode = "manual"
        sensors = self.get_gpu_sensors(adapter_index)
        return ActionResult(
            success=True,
            action="enable_gpu_manual_fan_control",
            reported_percent=sensors.fan.current_percent,
            reported_rpm=sensors.fan.rpm,
            data={"control_mode": "manual"},
        )

    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        return self.reset_gpu_fan_control(adapter_index)

    def reset_gpu_fan_control(self, adapter_index: int = 0) -> ActionResult:
        self._fan_mode = "auto"
        self._target_fan_percent = 35.0  # Safe auto baseline
        sensors = self.get_gpu_sensors(adapter_index)
        return ActionResult(
            success=True,
            action="reset_gpu_fan_control",
            reported_percent=sensors.fan.current_percent,
            reported_rpm=sensors.fan.rpm,
            temperature_c=sensors.temperature_c,
            data={"control_mode": "auto"},
        )

    def get_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        return {
            "vendor": "AMD",
            "driver_version": "31.0.21912.14",
            "branch": "Adrenalin 23.11.1",
            "simulation": True,
        }

    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        return {
            "part_number": "113-1E3660U-O51",
            "version": "015.050.002.001.000000",
            "date": "2018/04/10",
        }

    def shutdown(self) -> None:
        pass
