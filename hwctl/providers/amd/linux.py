"""AMD GPU Provider for Linux / Arch Linux via direct sysfs and hwmon.

Exposes direct PWM control, raw RPM telemetry, kernel logs, and VBIOS retrieval
without requiring proprietary user-space libraries.
"""

import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

from hwctl.core.exceptions import (
    DriverError,
    FanControlUnavailableError,
    HardwareNotFoundError,
    PermissionDeniedError,
)
from hwctl.core.models import ActionResult, FanStatus, GpuInfo, GpuSensors
from hwctl.core.safety import SafetyGuard
from hwctl.providers.base import BaseGpuProvider


class AmdLinuxProvider(BaseGpuProvider):
    """Native Linux provider interacting directly with amdgpu sysfs / hwmon nodes."""

    def __init__(self):
        self._card_path: Optional[Path] = None
        self._hwmon_path: Optional[Path] = None
        self._initialized = False

    @property
    def vendor_name(self) -> str:
        return "AMD"

    def is_available(self) -> bool:
        """Checks if a DRM device driven by amdgpu is present in sysfs."""
        if not Path("/sys/class/drm").exists():
            return False

        cards = self._discover_amdgpu_cards()
        return len(cards) > 0

    def _discover_amdgpu_cards(self) -> List[Path]:
        cards: List[Path] = []
        drm = Path("/sys/class/drm")
        if not drm.exists():
            return cards

        for entry in drm.glob("card[0-9]*"):
            device_dir = entry / "device"
            driver_link = device_dir / "driver"
            if driver_link.exists() and "amdgpu" in driver_link.resolve().name:
                cards.append(entry)
        return cards

    def initialize(self) -> None:
        cards = self._discover_amdgpu_cards()
        if not cards:
            raise HardwareNotFoundError("No AMD GPU driven by amdgpu driver was detected in /sys/class/drm.")

        self._card_path = cards[0]
        device_dir = self._card_path / "device"
        hwmon_dir = device_dir / "hwmon"

        if hwmon_dir.exists():
            hwmon_sub = list(hwmon_dir.glob("hwmon*"))
            if hwmon_sub:
                self._hwmon_path = hwmon_sub[0]

        self._initialized = True

    def _read_int(self, filename: str) -> Optional[int]:
        if not self._hwmon_path:
            return None
        p = self._hwmon_path / filename
        try:
            if p.exists():
                return int(p.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass
        return None

    def _read_str(self, filename: str) -> Optional[str]:
        base = self._hwmon_path or (self._card_path / "device" if self._card_path else None)
        if not base:
            return None
        p = base / filename
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return None

    def _write_str(self, filename: str, value: str) -> None:
        if not self._hwmon_path:
            raise FanControlUnavailableError("hwmon directory not found for AMD GPU.")
        p = self._hwmon_path / filename
        try:
            p.write_text(str(value).strip(), encoding="utf-8")
        except PermissionError:
            raise PermissionDeniedError(
                f"Writing to {p} requires root privileges (run with sudo or as root in Arch Linux)."
            )
        except OSError as e:
            raise DriverError(f"Failed to write '{value}' to {filename}: {e}")

    def get_gpu_info(self, adapter_index: int = 0) -> GpuInfo:
        if not self._initialized:
            self.initialize()

        vbios_ver = self._read_str("vbios_version")
        dev_dir = self._card_path / "device"
        model_name = "AMD Radeon GPU (amdgpu)"

        # Read PCI subsystem device ID if available
        sub_id = None
        sub_id_file = dev_dir / "subsystem_device"
        if sub_id_file.exists():
            try:
                sub_id = sub_id_file.read_text().strip()
            except OSError:
                pass

        return GpuInfo(
            adapter_index=adapter_index,
            vendor="AMD",
            model=model_name,
            vbios_version=vbios_ver or "Unknown",
            device_id=sub_id,
            is_primary=True,
        )

    def get_gpu_sensors(self, adapter_index: int = 0) -> GpuSensors:
        if not self._initialized:
            self.initialize()

        # Temperatures in millidegrees C
        t1 = self._read_int("temp1_input")
        t2 = self._read_int("temp2_input")
        core_temp = round(t1 / 1000.0, 1) if t1 is not None else None
        hotspot = round(t2 / 1000.0, 1) if t2 is not None else None

        # Power in microWatts
        p_raw = self._read_int("power1_average") or self._read_int("power1_input")
        power_w = round(p_raw / 1000000.0, 1) if p_raw is not None else None

        # GPU Busy percent
        dev_dir = self._card_path / "device" if self._card_path else None
        busy_file = dev_dir / "gpu_busy_percent" if dev_dir else None
        usage_pct = None
        if busy_file and busy_file.exists():
            try:
                usage_pct = float(busy_file.read_text().strip())
            except (ValueError, OSError):
                pass

        fan = self.get_gpu_fan_status(adapter_index)

        return GpuSensors(
            temperature_c=core_temp,
            hotspot_c=hotspot,
            usage_percent=usage_pct,
            power_w=power_w,
            fan=fan,
        )

    def get_gpu_fan_status(self, adapter_index: int = 0) -> FanStatus:
        if not self._initialized:
            self.initialize()

        rpm = self._read_int("fan1_input")
        pwm_raw = self._read_int("pwm1")
        pwm_enable = self._read_int("pwm1_enable")  # 1 = manual, 2 = auto

        current_pct = round((pwm_raw / 255.0) * 100.0, 1) if pwm_raw is not None else None
        mode_str = "manual" if pwm_enable == 1 else ("auto" if pwm_enable == 2 else "unknown")

        min_r = self._read_int("fan1_min")
        max_r = self._read_int("fan1_max")

        return FanStatus(
            target_percent=current_pct,
            current_percent=current_pct,
            rpm=rpm,
            control_mode=mode_str,
            min_percent=0.0,
            max_percent=100.0,
            min_rpm=min_r,
            max_rpm=max_r,
        )

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> ActionResult:
        if not self._initialized:
            self.initialize()

        validated = SafetyGuard.validate_fan_percent(percent)
        pwm_val = int(round((validated / 100.0) * 255.0))

        # 1. Enable manual mode (pwm1_enable = 1)
        self._write_str("pwm1_enable", "1")
        # 2. Set PWM value (0-255)
        self._write_str("pwm1", str(pwm_val))

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
        if not self._initialized:
            self.initialize()
        self._write_str("pwm1_enable", "1")
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
        if not self._initialized:
            self.initialize()
        # In amdgpu sysfs, pwm1_enable = 2 restores automatic kernel fan control
        self._write_str("pwm1_enable", "2")
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
            "driver": "amdgpu",
            "interface": "sysfs / hwmon",
            "hwmon_path": str(self._hwmon_path) if self._hwmon_path else None,
        }

    def get_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        ver = self._read_str("vbios_version")
        debug_vbios = Path("/sys/kernel/debug/dri/0/amdgpu_vbios")
        dumpable = debug_vbios.exists() and os.access(debug_vbios, os.R_OK)
        return {
            "version": ver or "Unknown",
            "debugfs_vbios_available": dumpable,
        }

    def get_kernel_dmesg_logs(self, max_lines: int = 30) -> List[str]:
        """Queries kernel ring buffer (dmesg) for amdgpu driver log messages."""
        try:
            res = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=3)
            lines = [l for l in res.stdout.splitlines() if "amdgpu" in l.lower()]
            return lines[-max_lines:]
        except Exception as e:
            return [f"Unable to read dmesg: {e}"]

    def shutdown(self) -> None:
        if self._initialized:
            try:
                self.reset_gpu_fan_control()
            except Exception:
                pass
