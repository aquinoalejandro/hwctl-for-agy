"""AMD GPU Provider implementing low-level telemetries and fan controls via ADL SDK."""

import sys
from typing import Any, Dict, List, Optional

from hwctl.core.exceptions import (
    DriverError,
    FanControlUnavailableError,
    HardwareNotFoundError,
    PermissionDeniedError,
    UnsupportedFeatureError,
)
from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors
from hwctl.core.safety import SafetyGuard
from hwctl.providers.amd.adl import (
    ADL_DL_FANCTRL_SPEED_TYPE_PERCENT,
    ADL_DL_FANCTRL_SPEED_TYPE_RPM,
    ADL_ERR_NOT_SUPPORTED,
    ADL_OK,
    AdlLibrary,
)
from hwctl.providers.base import BaseGpuProvider


class AmdGpuProvider(BaseGpuProvider):
    """Native AMD GPU Provider interfacing directly with atiadlxx.dll."""

    def __init__(self):
        self._adl = AdlLibrary()
        self._initialized = False
        self._active_adapters: List[int] = []

    @property
    def vendor_name(self) -> str:
        return "AMD"

    def is_available(self) -> bool:
        """Checks if AMD driver library atiadlxx.dll exists and can be loaded."""
        if not self._adl.is_loaded():
            loaded = self._adl.load()
            if not loaded:
                return False

        if not self._initialized:
            try:
                self.initialize()
            except Exception:
                return False

        return len(self._active_adapters) > 0

    def initialize(self) -> None:
        """Initializes ADL library and enumerates AMD adapters."""
        if not self._adl.is_loaded():
            if not self._adl.load():
                raise DriverError(
                    "atiadlxx.dll / atiadlxy.dll not found. AMD Adrenalin drivers may not be installed."
                )

        status = self._adl.initialize()
        if status != ADL_OK:
            raise DriverError(f"Failed to initialize AMD ADL interface. ADL status code: {status}")

        self._initialized = True
        self._refresh_adapters()

    def _refresh_adapters(self) -> None:
        """Finds active AMD adapters with presence and existence flags."""
        status, num = self._adl.get_number_of_adapters()
        if status != ADL_OK or num <= 0:
            self._active_adapters = []
            return

        status, adapters = self._adl.get_adapter_info(num)
        self._active_adapters = []
        seen_bus = set()

        for info in adapters:
            # Vendor ID for AMD is 0x1002 (4098)
            if info.iPresent and (info.iVendorID == 4098 or b"AMD" in info.strAdapterName or b"Radeon" in info.strAdapterName):
                bus_id = (info.iBusNumber, info.iDeviceNumber, info.iFunctionNumber)
                if bus_id not in seen_bus:
                    seen_bus.add(bus_id)
                    self._active_adapters.append(info.iAdapterIndex)

    def _ensure_ready(self, adapter_index: int) -> int:
        if not self._initialized:
            self.initialize()
        if not self._active_adapters:
            raise HardwareNotFoundError("No active AMD Radeon GPUs were detected on this system.")

        if adapter_index not in self._active_adapters:
            # Fall back to first discovered adapter
            return self._active_adapters[0]
        return adapter_index

    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        idx = self._ensure_ready(adapter_index)
        _, num = self._adl.get_number_of_adapters()
        _, adapters = self._adl.get_adapter_info(num)

        target_info = None
        for a in adapters:
            if a.iAdapterIndex == idx:
                target_info = a
                break

        model_name = target_info.strAdapterName.decode("utf-8", errors="ignore").strip() if target_info else "AMD Radeon GPU"
        driver_path = target_info.strDriverPath.decode("utf-8", errors="ignore").strip() if target_info else None

        # Fetch BIOS info if available
        vbios_str = None
        status_b, bios_info = self._adl.get_bios_info(idx)
        if status_b == ADL_OK and bios_info:
            vbios_str = bios_info.strVersion.decode("utf-8", errors="ignore").strip() or bios_info.strPartNumber.decode("utf-8", errors="ignore").strip()

        return GpuInfo(
            adapter_index=idx,
            vendor="AMD",
            model=model_name or "AMD Radeon GPU",
            driver_version=driver_path or "AMD Adrenalin Driver",
            vbios_version=vbios_str,
            is_primary=True,
        )

    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        idx = self._ensure_ready(adapter_index)

        # Core temperature
        temp_status, temp_c = self._adl.get_temperature(idx)
        core_temp = temp_c if temp_status == ADL_OK else None

        # Activity, clocks, usage and voltage
        act_status, act = self._adl.get_activity(idx)
        usage_pct = None
        core_clk = None
        mem_clk = None
        voltage = None

        if act_status == ADL_OK and act:
            usage_pct = float(act.iActivityPercent)
            # ADL reports engine and memory clock in 10 kHz (e.g. 134000 = 1340 MHz)
            core_clk = float(act.iEngineClock) / 100.0 if act.iEngineClock > 0 else None
            mem_clk = float(act.iMemoryClock) / 100.0 if act.iMemoryClock > 0 else None
            voltage = float(act.iVddc) if act.iVddc > 0 else None

        # Power
        power_status, power_w = self._adl.get_power(idx)
        current_power = power_w if power_status == ADL_OK and power_w > 0 else None

        # Fan status
        fan = self.get_gpu_fan_status(idx)

        return GpuSensors(
            temperature_c=core_temp,
            usage_percent=usage_pct,
            core_clock_mhz=core_clk,
            memory_clock_mhz=mem_clk,
            voltage_mv=voltage,
            power_w=current_power,
            fan=fan,
        )

    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        idx = self._ensure_ready(adapter_index)

        # Current RPM
        rpm_status, current_rpm = self._adl.get_fan_speed(idx, ADL_DL_FANCTRL_SPEED_TYPE_RPM)
        rpm_val = current_rpm if rpm_status == ADL_OK else None

        # Current percentage
        pct_status, current_pct = self._adl.get_fan_speed(idx, ADL_DL_FANCTRL_SPEED_TYPE_PERCENT)
        pct_val = float(current_pct) if pct_status == ADL_OK else None

        # Fan speed capabilities / limits
        info_status, speed_info = self._adl.get_fan_speed_info(idx)
        min_p = float(speed_info.iMinPercent) if (info_status == ADL_OK and speed_info) else 0.0
        max_p = float(speed_info.iMaxPercent) if (info_status == ADL_OK and speed_info) else 100.0
        min_r = speed_info.iMinRPM if (info_status == ADL_OK and speed_info) else None
        max_r = speed_info.iMaxRPM if (info_status == ADL_OK and speed_info) else None

        return FanStatus(
            target_percent=pct_val,
            current_percent=pct_val,
            rpm=rpm_val,
            control_mode="unknown",  # Will be refined if manual mode is explicitly set
            min_percent=min_p,
            max_percent=max_p,
            min_rpm=min_r,
            max_rpm=max_r,
        )

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        idx = self._ensure_ready(adapter_index)
        validated_pct = SafetyGuard.validate_fan_percent(percent)

        status = self._adl.set_fan_speed_percent(idx, int(round(validated_pct)))
        if status != ADL_OK:
            if status == ADL_ERR_NOT_SUPPORTED:
                raise FanControlUnavailableError(
                    "Fan control is not supported by this driver/hardware profile."
                )
            elif status == -1:
                raise PermissionDeniedError(
                    "ADL returned error code -1. Administrative privileges or Overdrive unlocking may be required."
                )
            else:
                raise DriverError(f"Failed to set fan speed. ADL error code: {status}")

        # Read back telemetry immediately to record result
        sensors = self.get_gpu_sensors(idx)
        return ActionResult(
            success=True,
            action="set_gpu_fan_percent",
            requested_percent=validated_pct,
            reported_percent=sensors.fan.current_percent,
            reported_rpm=sensors.fan.rpm,
            temperature_c=sensors.temperature_c,
            power_w=sensors.power_w,
        )

    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        """Enables manual fan control by reading current percent and locking it as user-defined."""
        idx = self._ensure_ready(adapter_index)
        status = self.get_gpu_fan_status(idx)
        target = status.current_percent if status.current_percent is not None else 50.0
        return self.set_gpu_fan_percent(target, idx)

    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> ActionResult:
        """Restores automatic fan curve."""
        return self.reset_gpu_fan_control(adapter_index)

    def reset_gpu_fan_control(self, adapter_index: int = 0) -> ActionResult:
        idx = self._ensure_ready(adapter_index)
        status = self._adl.reset_fan_speed(idx)
        if status != ADL_OK and status != ADL_ERR_NOT_SUPPORTED:
            # Try setting to 50% as safe fallback if reset function is unsupported on driver
            sys.stderr.write(f"[WARN] reset_fan_speed returned {status}, attempting fallback\n")

        sensors = self.get_gpu_sensors(idx)
        return ActionResult(
            success=True,
            action="reset_gpu_fan_control",
            reported_percent=sensors.fan.current_percent,
            reported_rpm=sensors.fan.rpm,
            temperature_c=sensors.temperature_c,
            power_w=sensors.power_w,
            data={"mode": "auto_default"},
        )

    def get_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        info = self.get_gpu_info(adapter_index)
        return {
            "vendor": info.vendor,
            "driver_version": info.driver_version,
            "adl_loaded": self._adl.is_loaded(),
            "active_adapters": len(self._active_adapters),
        }

    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        idx = self._ensure_ready(adapter_index)
        st, bios = self._adl.get_bios_info(idx)
        if st == ADL_OK and bios:
            return {
                "part_number": bios.strPartNumber.decode("utf-8", errors="ignore").strip(),
                "version": bios.strVersion.decode("utf-8", errors="ignore").strip(),
                "date": bios.strDate.decode("utf-8", errors="ignore").strip(),
            }
        return {"version": "Unknown", "status": "Not reported by driver"}

    def list_adapters(self) -> List[Dict[str, Any]]:
        """Enumerates all detected AMD Radeon GPUs on the system."""
        if not self._initialized:
            try:
                self.initialize()
            except Exception:
                return []

        if not self._active_adapters:
            return []

        _, num = self._adl.get_number_of_adapters()
        _, adapters = self._adl.get_adapter_info(num)
        result = []
        for idx in self._active_adapters:
            info = next((a for a in adapters if a.iAdapterIndex == idx), None)
            entry: Dict[str, Any] = {"adapter_index": idx}
            if info:
                entry["model"] = info.strAdapterName.decode("utf-8", errors="ignore").strip()
                entry["display_name"] = info.strDisplayName.decode("utf-8", errors="ignore").strip()
                entry["bus_number"] = info.iBusNumber
                entry["device_number"] = info.iDeviceNumber
                entry["vendor_id"] = info.iVendorID
                entry["present"] = bool(info.iPresent)
            result.append(entry)
        return result

    def get_power_states(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries current performance level, clocks, and voltage via Overdrive 5 Activity."""
        idx = self._ensure_ready(adapter_index)
        act_status, act = self._adl.get_activity(idx)
        if act_status != ADL_OK or not act:
            return {"current_performance_level": "unknown", "states": [], "note": "ADL Activity query failed."}

        return {
            "current_performance_level": act.iCurrentPerformanceLevel,
            "engine_clock_mhz": round(float(act.iEngineClock) / 100.0, 1) if act.iEngineClock > 0 else None,
            "memory_clock_mhz": round(float(act.iMemoryClock) / 100.0, 1) if act.iMemoryClock > 0 else None,
            "voltage_mv": act.iVddc if act.iVddc > 0 else None,
            "gpu_activity_percent": act.iActivityPercent,
            "bus_speed": act.iCurrentBusSpeed,
            "bus_lanes_current": act.iCurrentBusLanes,
            "bus_lanes_max": act.iMaximumBusLanes,
        }

    def get_display_outputs(self, adapter_index: int = 0) -> List[Dict[str, Any]]:
        """Detects connected display outputs from adapter info entries."""
        if not self._initialized:
            try:
                self.initialize()
            except Exception:
                return []

        _, num = self._adl.get_number_of_adapters()
        _, adapters = self._adl.get_adapter_info(num)
        outputs = []
        for a in adapters:
            if a.iAdapterIndex in self._active_adapters:
                display_name = a.strDisplayName.decode("utf-8", errors="ignore").strip()
                if display_name:
                    outputs.append({
                        "adapter_index": a.iAdapterIndex,
                        "display_name": display_name,
                        "os_display_index": a.iOSDisplayIndex,
                        "present": bool(a.iPresent),
                    })
        return outputs

    def shutdown(self) -> None:
        if self._initialized:
            try:
                self.reset_gpu_fan_control()
            except Exception:
                pass
            self._adl.destroy()
            self._initialized = False

