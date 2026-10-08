"""Windows Host System Provider.

Extracts operating system version, CPU, RAM, motherboard identification,
and monitors running processes that may conflict with GPU hardware control.
"""

import platform
import sys
from typing import List, Optional
import winreg

import psutil

from hwctl.core.models import ProcessInfo, SystemInfo
from hwctl.providers.base import BaseSystemProvider

# Known hardware tuning/monitoring executables that could conflict with direct GPU control
HARDWARE_CONFLICT_TOOLS = {
    "msiafterburner.exe",
    "radeonsoftware.exe",
    "amdfendrsr.exe",
    "amdow.exe",
    "fancontrol.exe",
    "gpu-z.exe",
    "furmark.exe",
    "aida64.exe",
    "hwinfo64.exe",
    "precisionx_server.exe",
    "gputweak.exe",
    "nzxt cam.exe",
    "corsairicue.exe",
}


class WindowsSystemProvider(BaseSystemProvider):
    """Queries Windows OS metrics and process activity."""

    def _get_reg_value(self, key_path: str, value_name: str) -> Optional[str]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                val, _ = winreg.QueryValueEx(key, value_name)
                return str(val).strip()
        except OSError:
            return None

    def get_system_info(self) -> SystemInfo:
        # Motherboard
        mb_vendor = self._get_reg_value(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardManufacturer")
        mb_product = self._get_reg_value(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardProduct")
        if not mb_vendor:
            mb_vendor = self._get_reg_value(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemManufacturer")
        if not mb_product:
            mb_product = self._get_reg_value(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemProductName")

        # CPU
        cpu_name = self._get_reg_value(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
        if not cpu_name:
            cpu_name = platform.processor() or "Unknown CPU"

        phys_cores = psutil.cpu_count(logical=False) or 1
        log_cores = psutil.cpu_count(logical=True) or 1

        # RAM
        vm = psutil.virtual_memory()
        total_ram_mb = round(vm.total / (1024 * 1024), 1)
        avail_ram_mb = round(vm.available / (1024 * 1024), 1)

        # OS
        win_version = platform.version()
        win_release = platform.release()

        # Processes
        procs = self.get_relevant_processes()

        return SystemInfo(
            os_name="Windows",
            os_version=win_release,
            os_build=win_version,
            cpu_model=cpu_name,
            cpu_cores_physical=phys_cores,
            cpu_cores_logical=log_cores,
            ram_total_mb=total_ram_mb,
            ram_available_mb=avail_ram_mb,
            motherboard_vendor=mb_vendor,
            motherboard_product=mb_product,
            relevant_processes=procs,
        )

    def get_relevant_processes(self) -> List[ProcessInfo]:
        """Identifies hardware tuning tools and top resource-consuming processes."""
        relevant: List[ProcessInfo] = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                name = (proc.info.get("name") or "").lower()
                is_hw_tool = name in HARDWARE_CONFLICT_TOOLS
                mem_mb = round((proc.info["memory_info"].rss if proc.info.get("memory_info") else 0) / (1024 * 1024), 1)
                cpu_pct = proc.info.get("cpu_percent") or 0.0

                # Include if it is a known GPU/hardware utility or consuming notable CPU (> 15%)
                if is_hw_tool or cpu_pct > 15.0:
                    relevant.append(
                        ProcessInfo(
                            pid=proc.info["pid"],
                            name=proc.info.get("name") or "unknown",
                            cpu_percent=round(cpu_pct, 1),
                            memory_mb=mem_mb,
                            is_hardware_tool=is_hw_tool,
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort so hardware tools appear first, followed by highest CPU consumers
        relevant.sort(key=lambda p: (not p.is_hardware_tool, -p.cpu_percent))
        return relevant[:20]  # Cap at top 20
