"""HardwareController - Central API for Antigravity AI Agent.

Orchestrates hardware querying, telemetry, validation, rollback, and safety guards.
Guarantees consistent, structured JSON responses for every tool call.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from hwctl.core.exceptions import HwctlError, InvalidParameterError, SafetyViolationError
from hwctl.core.logger import audit_logger
from hwctl.core.models import ActionResult, EnvironmentHealth, current_iso_timestamp
from hwctl.core.registry import ProviderRegistry
from hwctl.core.safety import RollbackManager, SafetyGuard
from hwctl.experiments.fan_step import FanStepExperiment
from hwctl.experiments.stress import GpuStressGenerator, ThermalStressExperiment
from hwctl.providers.base import BaseGpuProvider, BaseSystemProvider


class HardwareController:
    """The unified tool controller consumed by Antigravity."""

    def __init__(
        self,
        provider_name: Optional[str] = None,
        mock_fault_mode: str = "none",
        registry: Optional[ProviderRegistry] = None,
    ):
        self.registry = registry or ProviderRegistry()
        if mock_fault_mode != "none":
            self.registry.set_mock_fault_mode(mock_fault_mode)

        self._force_provider = provider_name
        self._rollback_manager = RollbackManager()
        self._stress_generator: Optional[GpuStressGenerator] = None

    def _get_gpu(self) -> BaseGpuProvider:
        return self.registry.get_gpu_provider(force_provider=self._force_provider)

    def _get_sys(self) -> BaseSystemProvider:
        return self.registry.get_system_provider()

    def _format_error(self, action: str, err: Exception) -> Dict[str, Any]:
        """Formats errors into the standardized JSON error contract."""
        if isinstance(err, HwctlError):
            err_dict = err.to_dict()
        else:
            err_dict = {
                "code": "EXECUTION_ERROR",
                "message": str(err),
            }

        audit_logger.log_event(
            event_type="error",
            tool=action,
            error=err_dict,
        )

        return {
            "success": False,
            "action": action,
            "error": err_dict,
            "timestamp": current_iso_timestamp(),
        }

    # ==========================
    # Read Actions (Queries)
    # ==========================

    def get_system_info(self) -> Dict[str, Any]:
        """Queries host OS, CPU, RAM, and relevant running processes."""
        t0 = time.time()
        try:
            sys_info = self._get_sys().get_system_info()
            res = {
                "success": True,
                "action": "get_system_info",
                "timestamp": current_iso_timestamp(),
                "data": sys_info.to_dict(),
            }
            audit_logger.log_event(
                event_type="query",
                tool="get_system_info",
                result={"success": True},
                duration_ms=(time.time() - t0) * 1000,
            )
            return res
        except Exception as e:
            return self._format_error("get_system_info", e)

    def get_gpu_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries GPU model, vendor, driver, VRAM, and VBIOS."""
        t0 = time.time()
        try:
            gpu_info = self._get_gpu().get_gpu_info(adapter_index)
            res = {
                "success": True,
                "action": "get_gpu_info",
                "timestamp": current_iso_timestamp(),
                "data": gpu_info.to_dict(),
            }
            audit_logger.log_event(
                event_type="query",
                tool="get_gpu_info",
                parameters={"adapter_index": adapter_index},
                result={"success": True},
                duration_ms=(time.time() - t0) * 1000,
            )
            return res
        except Exception as e:
            return self._format_error("get_gpu_info", e)

    def get_gpu_sensors(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries real-time GPU sensor readings (temperatures, clocks, fan, power)."""
        t0 = time.time()
        try:
            sensors = self._get_gpu().get_gpu_sensors(adapter_index)
            res = {
                "success": True,
                "action": "get_gpu_sensors",
                "timestamp": current_iso_timestamp(),
                "data": sensors.to_dict(),
            }
            audit_logger.log_event(
                event_type="query",
                tool="get_gpu_sensors",
                parameters={"adapter_index": adapter_index},
                result={"success": True},
                duration_ms=(time.time() - t0) * 1000,
            )
            return res
        except Exception as e:
            return self._format_error("get_gpu_sensors", e)

    def get_gpu_fan_status(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries fan speed percentage, RPM, and manual/auto control state."""
        t0 = time.time()
        try:
            fan_status = self._get_gpu().get_gpu_fan_status(adapter_index)
            res = {
                "success": True,
                "action": "get_gpu_fan_status",
                "timestamp": current_iso_timestamp(),
                "data": fan_status.to_dict(),
            }
            audit_logger.log_event(
                event_type="query",
                tool="get_gpu_fan_status",
                parameters={"adapter_index": adapter_index},
                result={"success": True},
                duration_ms=(time.time() - t0) * 1000,
            )
            return res
        except Exception as e:
            return self._format_error("get_gpu_fan_status", e)

    def get_gpu_driver_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries driver version and interface capabilities."""
        try:
            data = self._get_gpu().get_driver_info(adapter_index)
            return {
                "success": True,
                "action": "get_gpu_driver_info",
                "timestamp": current_iso_timestamp(),
                "data": data,
            }
        except Exception as e:
            return self._format_error("get_gpu_driver_info", e)

    def get_gpu_vbios_info(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Queries safe VBIOS and firmware version strings."""
        try:
            data = self._get_gpu().get_vbios_info(adapter_index)
            return {
                "success": True,
                "action": "get_gpu_vbios_info",
                "timestamp": current_iso_timestamp(),
                "data": data,
            }
        except Exception as e:
            return self._format_error("get_gpu_vbios_info", e)

    # ==========================
    # Write Actions (Mutations)
    # ==========================

    def set_gpu_fan_percent(self, percent: float, adapter_index: int = 0) -> Dict[str, Any]:
        """Sets GPU fan speed percentage [0-100] with validation and rollback capture."""
        t0 = time.time()
        action_name = "set_gpu_fan_percent"
        try:
            validated = SafetyGuard.validate_fan_percent(percent)
            gpu = self._get_gpu()

            # Capture state before mutation for safety rollback
            current_fan = gpu.get_gpu_fan_status(adapter_index)
            self._rollback_manager.capture_state(
                state={"fan": current_fan.to_dict()},
                rollback_action=lambda: gpu.reset_gpu_fan_control(adapter_index),
            )

            # Apply change
            action_result = gpu.set_gpu_fan_percent(validated, adapter_index)
            res = action_result.to_dict()

            audit_logger.log_event(
                event_type="action",
                tool=action_name,
                parameters={"requested_percent": validated, "adapter_index": adapter_index},
                before_state=current_fan.to_dict(),
                after_state={"reported_percent": action_result.reported_percent, "reported_rpm": action_result.reported_rpm},
                result={"success": True},
                duration_ms=(time.time() - t0) * 1000,
            )
            return res
        except Exception as e:
            return self._format_error(action_name, e)

    def enable_gpu_manual_fan_control(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Unlocks manual fan control."""
        action_name = "enable_gpu_manual_fan_control"
        try:
            gpu = self._get_gpu()
            current_fan = gpu.get_gpu_fan_status(adapter_index)
            self._rollback_manager.capture_state(
                state={"fan": current_fan.to_dict()},
                rollback_action=lambda: gpu.reset_gpu_fan_control(adapter_index),
            )
            action_result = gpu.enable_gpu_manual_fan_control(adapter_index)
            res = action_result.to_dict()
            audit_logger.log_event(event_type="action", tool=action_name, result={"success": True})
            return res
        except Exception as e:
            return self._format_error(action_name, e)

    def disable_gpu_manual_fan_control(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Restores driver automatic fan control."""
        action_name = "disable_gpu_manual_fan_control"
        try:
            action_result = self._get_gpu().disable_gpu_manual_fan_control(adapter_index)
            self._rollback_manager.clear()
            res = action_result.to_dict()
            audit_logger.log_event(event_type="action", tool=action_name, result={"success": True})
            return res
        except Exception as e:
            return self._format_error(action_name, e)

    def reset_gpu_fan_control(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Restores default automatic fan speed curve."""
        action_name = "reset_gpu_fan_control"
        try:
            action_result = self._get_gpu().reset_gpu_fan_control(adapter_index)
            self._rollback_manager.clear()
            res = action_result.to_dict()
            audit_logger.log_event(event_type="action", tool=action_name, result={"success": True})
            return res
        except Exception as e:
            return self._format_error(action_name, e)

    # ==========================
    # Controlled Experiments
    # ==========================

    def run_fan_test(
        self,
        steps: Optional[List[float]] = None,
        hold_seconds: float = 5.0,
        sample_interval_seconds: float = 1.0,
        adapter_index: int = 0,
        restore_on_finish: bool = True,
    ) -> Dict[str, Any]:
        """Executes a multi-step fan response test, capturing samples at each interval."""
        action_name = "run_fan_test"
        try:
            experiment = FanStepExperiment(
                gpu_provider=self._get_gpu(),
                adapter_index=adapter_index,
                rollback_manager=self._rollback_manager,
            )
            test_result = experiment.run(
                steps=steps,
                hold_duration_seconds=hold_seconds,
                sample_interval_seconds=sample_interval_seconds,
                restore_on_finish=restore_on_finish,
            )
            return {
                "success": test_result.success,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": test_result.to_dict(),
            }
        except Exception as e:
            return self._format_error(action_name, e)

    # ==========================
    # Diagnostic Snapshots
    # ==========================

    def create_diagnostic_snapshot(self, adapter_index: int = 0) -> Dict[str, Any]:
        """Captures a synchronized snapshot of system, GPU telemetry, and running processes."""
        action_name = "create_diagnostic_snapshot"
        try:
            sys_info = self._get_sys().get_system_info()
            gpu_info = self._get_gpu().get_gpu_info(adapter_index)
            sensors = self._get_gpu().get_gpu_sensors(adapter_index)
            driver = self._get_gpu().get_driver_info(adapter_index)
            vbios = self._get_gpu().get_vbios_info(adapter_index)

            snapshot = {
                "timestamp": current_iso_timestamp(),
                "system": sys_info.to_dict(),
                "gpu": gpu_info.to_dict(),
                "driver": driver,
                "vbios": vbios,
                "sensors": sensors.to_dict(),
            }

            audit_logger.log_event(
                event_type="action",
                tool=action_name,
                parameters={"adapter_index": adapter_index},
                result={"success": True},
            )

            return {
                "success": True,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": snapshot,
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def create_diagnostic_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Saves a JSON diagnostic snapshot to disk."""
        snapshot_res = self.create_diagnostic_snapshot()
        if not snapshot_res.get("success"):
            return snapshot_res

        out_file = Path(output_path) if output_path else Path("logs") / f"snapshot_{int(time.time())}.json"
        try:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(snapshot_res["data"], f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "action": "create_diagnostic_report",
                "timestamp": current_iso_timestamp(),
                "data": {"file_path": str(out_file.resolve()), "snapshot": snapshot_res["data"]},
            }
        except Exception as e:
            return self._format_error("create_diagnostic_report", e)

    # ==========================
    # System & Stress Actions
    # ==========================

    def check_environment(self) -> Dict[str, Any]:
        """Validates OS type (Windows vs Linux / Arch Linux), elevation, drivers, and potential software conflicts."""
        action_name = "check_environment"
        try:
            import os
            import platform

            is_linux = platform.system() == "Linux"
            is_admin = False
            notes = []

            if is_linux:
                is_admin = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
                adl_available = False
                opencl_available = Path("/usr/lib/libOpenCL.so").exists() or Path("/usr/lib64/libOpenCL.so").exists() or Path("/etc/OpenCL").exists()

                distro_name = "Linux"
                try:
                    if hasattr(platform, "freedesktop_os_release"):
                        distro_name = platform.freedesktop_os_release().get("PRETTY_NAME") or platform.freedesktop_os_release().get("NAME") or "Linux"
                except Exception:
                    pass

                notes.append(f"Detected OS: {distro_name} (Kernel {platform.release()}).")
                if "arch" in distro_name.lower():
                    notes.append("Arch Linux detected: provides maximum freedom via direct sysfs/hwmon nodes and dmesg.")

                if is_admin:
                    notes.append("Running as root (UID 0): direct PWM writing and hardware overrides are fully authorized.")
                else:
                    notes.append("Running as standard user: writing to /sys/class/drm/*/device/hwmon/pwm1 requires sudo or root.")

                # Check amdgpu ppfeaturemask
                pp_file = Path("/sys/module/amdgpu/parameters/ppfeaturemask")
                if pp_file.exists():
                    try:
                        mask = pp_file.read_text().strip()
                        notes.append(f"amdgpu.ppfeaturemask={mask} (OverDrive power & clock mask).")
                    except OSError:
                        pass
            else:
                import ctypes
                try:
                    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
                except Exception:
                    pass

                adl_available = Path("C:/Windows/System32/atiadlxx.dll").exists() or Path("C:/Windows/System32/atiadlxy.dll").exists()
                opencl_available = Path("C:/Windows/System32/OpenCL.dll").exists()

                notes.append("Detected OS: Windows.")
                if not is_admin:
                    notes.append("Process is not elevated as Administrator. Writing fan speeds to AMD hardware will likely fail with error -1.")
                if not adl_available:
                    notes.append("atiadlxx.dll not found in System32. AMD Adrenalin driver may not be installed.")

            # Detect conflicting tuning tools
            sys_info = self._get_sys().get_system_info()
            conflicts = [p.name for p in sys_info.relevant_processes if p.is_hardware_tool]
            if conflicts:
                notes.append(f"Detected hardware tuning tools running: {', '.join(conflicts)}. They may overwrite manual fan settings.")

            gpu_vendor = self._get_gpu().vendor_name

            health = EnvironmentHealth(
                is_admin=is_admin,
                adl_available=adl_available,
                opencl_available=opencl_available,
                active_gpu_vendor=gpu_vendor,
                conflicting_processes=conflicts,
                notes=notes,
            )

            return {
                "success": True,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": health.to_dict(),
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def get_kernel_logs(self, max_lines: int = 50) -> Dict[str, Any]:
        """Fetches kernel logs (dmesg) regarding the GPU subsystem (on Linux/Arch Linux)."""
        action_name = "get_kernel_logs"
        try:
            gpu = self._get_gpu()
            if hasattr(gpu, "get_kernel_dmesg_logs"):
                logs = gpu.get_kernel_dmesg_logs(max_lines=max_lines)
            else:
                logs = ["Kernel dmesg logs are only available under Linux / Arch Linux."]

            return {
                "success": True,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": {"logs": logs, "count": len(logs)},
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def start_gpu_stress(self, duration_seconds: float = 30.0) -> Dict[str, Any]:
        """Launches continuous GPU compute load in the background with auto-timeout."""
        action_name = "start_gpu_stress"
        try:
            duration = SafetyGuard.validate_duration(duration_seconds)
            if self._stress_generator is None:
                self._stress_generator = GpuStressGenerator()

            gpu = self._get_gpu()
            if hasattr(gpu, "set_simulated_load"):
                gpu.set_simulated_load(True)

            self._stress_generator.start(duration_seconds=duration)
            sensors = gpu.get_gpu_sensors()

            return {
                "success": True,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": {
                    "running": True,
                    "max_duration_seconds": duration,
                    "hardware_accelerated": self._stress_generator.has_hardware_acceleration,
                    "sensors_now": sensors.to_dict(),
                },
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def stop_gpu_stress(self) -> Dict[str, Any]:
        """Halts active background GPU stress immediately."""
        action_name = "stop_gpu_stress"
        try:
            if self._stress_generator:
                self._stress_generator.stop()

            gpu = self._get_gpu()
            if hasattr(gpu, "set_simulated_load"):
                gpu.set_simulated_load(False)

            sensors = gpu.get_gpu_sensors()
            return {
                "success": True,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": {
                    "running": False,
                    "sensors_now": sensors.to_dict(),
                },
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def run_thermal_stress_test(
        self,
        duration_seconds: float = 20.0,
        sample_interval_seconds: float = 1.0,
        emergency_temp_c: float = 90.0,
        emergency_hotspot_c: float = 105.0,
        adapter_index: int = 0,
    ) -> Dict[str, Any]:
        """Runs controlled stress test, sampling telemetry with an emergency thermal tripwire."""
        action_name = "run_thermal_stress_test"
        try:
            experiment = ThermalStressExperiment(
                gpu_provider=self._get_gpu(),
                adapter_index=adapter_index,
            )
            result = experiment.run(
                duration_seconds=duration_seconds,
                sample_interval_seconds=sample_interval_seconds,
                emergency_temp_c=emergency_temp_c,
                emergency_hotspot_c=emergency_hotspot_c,
            )
            return {
                "success": result.success,
                "action": action_name,
                "timestamp": current_iso_timestamp(),
                "data": result.to_dict(),
            }
        except Exception as e:
            return self._format_error(action_name, e)

    def shutdown(self) -> None:
        """Cleanly tears down controller, halts stress workers, and ensures rollback."""
        try:
            self.stop_gpu_stress()
            self._rollback_manager.execute_rollback()
            self._get_gpu().shutdown()
        except Exception:
            pass
