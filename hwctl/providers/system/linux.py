"""Linux Host System Provider (with special support for Arch Linux and other distributions).

Extracts distribution details, kernel version, CPU, RAM, motherboard DMI,
and monitors running processes.
"""

from pathlib import Path
import platform
from typing import Dict, List, Optional

import psutil

from hwctl.core.models import ProcessInfo, SystemInfo
from hwctl.providers.base import BaseSystemProvider

# Hardware utilities on Linux that might conflict with direct fan control
LINUX_HARDWARE_CONFLICT_TOOLS = {
    "corectrl",
    "lact",
    "gwe",
    "greenwithenvy",
    "radeon-profile",
    "coolercontrold",
    "fancontrol",
}


class LinuxSystemProvider(BaseSystemProvider):
    """Queries Linux OS metrics, distro identity, and hardware topology."""

    def _get_os_info(self) -> Dict[str, str]:
        distro_name = "Linux"
        distro_version = platform.release()

        # Try freedesktop os-release (Arch, Fedora, Ubuntu, Debian, etc.)
        try:
            if hasattr(platform, "freedesktop_os_release"):
                info = platform.freedesktop_os_release()
                distro_name = info.get("PRETTY_NAME") or info.get("NAME") or "Linux"
                distro_version = info.get("VERSION_ID") or platform.release()
            elif Path("/etc/os-release").exists():
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            distro_name = line.strip().split("=", 1)[1].strip('"\'')
                        elif line.startswith("VERSION_ID="):
                            distro_version = line.strip().split("=", 1)[1].strip('"\'')
        except Exception:
            pass

        return {"name": distro_name, "version": distro_version, "kernel": platform.release()}

    def _read_dmi(self, filename: str) -> Optional[str]:
        path = Path(f"/sys/class/dmi/id/{filename}")
        try:
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        except (PermissionError, OSError):
            pass
        return None

    def get_system_info(self) -> SystemInfo:
        os_info = self._get_os_info()

        # Motherboard via DMI sysfs
        mb_vendor = self._read_dmi("board_vendor") or self._read_dmi("sys_vendor")
        mb_product = self._read_dmi("board_name") or self._read_dmi("product_name")

        # CPU info
        cpu_name = platform.processor() or "Unknown CPU"
        try:
            cpuinfo = Path("/proc/cpuinfo")
            if cpuinfo.exists():
                for line in cpuinfo.read_text(encoding="utf-8").splitlines():
                    if "model name" in line:
                        cpu_name = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        phys_cores = psutil.cpu_count(logical=False) or 1
        log_cores = psutil.cpu_count(logical=True) or 1

        # Memory
        vm = psutil.virtual_memory()
        total_ram_mb = round(vm.total / (1024 * 1024), 1)
        avail_ram_mb = round(vm.available / (1024 * 1024), 1)

        procs = self.get_relevant_processes()

        return SystemInfo(
            os_name=os_info["name"],
            os_version=os_info["version"],
            os_build=f"Kernel {os_info['kernel']}",
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
        relevant: List[ProcessInfo] = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                name = (proc.info.get("name") or "").lower()
                is_hw_tool = name in LINUX_HARDWARE_CONFLICT_TOOLS
                mem_mb = round((proc.info["memory_info"].rss if proc.info.get("memory_info") else 0) / (1024 * 1024), 1)
                cpu_pct = proc.info.get("cpu_percent") or 0.0

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

        relevant.sort(key=lambda p: (not p.is_hardware_tool, -p.cpu_percent))
        return relevant[:20]
