"""Windows Host System Provider.

Extracts operating system version, CPU, RAM, motherboard identification,
and monitors running processes that may conflict with GPU hardware control.
"""

import platform
import sys
from typing import Any, Dict, List, Optional
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

    def get_event_logs(self, source_filter: str = "Display", max_entries: int = 30) -> List[Dict[str, Any]]:
        """Reads Windows Event Log entries related to GPU/display subsystem.

        Searches System and Application logs for events from display/GPU driver sources
        such as 'Display', 'nvlddmkm', 'amdwddmg', 'dxgkrnl', 'Kernel-Power', etc.
        """
        import json as _json
        import subprocess

        # Known event log sources relevant to GPU diagnostics
        gpu_sources = [
            "Display",
            "nvlddmkm",
            "amdwddmg",
            "atikmdag",
            "dxgkrnl",
            "dxgmms1",
            "dxgmms2",
            "Kernel-Power",
            "volmgr",
            "disk",
            "amdgpu",
        ]

        # Build the source match filter from input + known GPU sources
        filter_sources = list({source_filter.lower()} | {s.lower() for s in gpu_sources})

        ps_script = f"""
$events = @()
try {{
    $sysEvents = Get-WinEvent -FilterHashtable @{{LogName='System'; Level=1,2,3; StartTime=(Get-Date).AddDays(-7)}} -MaxEvents {max_entries * 3} -ErrorAction SilentlyContinue
    if ($sysEvents) {{ $events += $sysEvents }}
}} catch {{}}
try {{
    $appEvents = Get-WinEvent -FilterHashtable @{{LogName='Application'; Level=1,2,3; StartTime=(Get-Date).AddDays(-7)}} -MaxEvents {max_entries * 2} -ErrorAction SilentlyContinue
    if ($appEvents) {{ $events += $appEvents }}
}} catch {{}}

$filterSources = @({','.join('"' + s + '"' for s in filter_sources)})
$filtered = $events | Where-Object {{
    $src = $_.ProviderName.ToLower()
    $msg = $_.Message.ToLower()
    ($filterSources -contains $src) -or ($msg -match 'gpu|display|graphics|tdr|dxgk|amdgpu|radeon|nvidia|d3d|directx')
}} | Select-Object -First {max_entries}

$result = $filtered | ForEach-Object {{
    @{{
        TimeCreated = $_.TimeCreated.ToString('o')
        ProviderName = $_.ProviderName
        Id = $_.Id
        LevelDisplayName = $_.LevelDisplayName
        Message = if ($_.Message.Length -gt 500) {{ $_.Message.Substring(0,500) + '...' }} else {{ $_.Message }}
    }}
}}
$result | ConvertTo-Json -Depth 3 -Compress
"""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []

            parsed = _json.loads(result.stdout.strip())
            if isinstance(parsed, dict):
                parsed = [parsed]
            return parsed[:max_entries]
        except Exception:
            return []

    def get_display_info(self) -> List[Dict[str, Any]]:
        """Enumerates connected display devices via Windows registry / WMI."""
        import subprocess
        import json as _json

        ps_script = """
$monitors = Get-CimInstance -ClassName Win32_DesktopMonitor -ErrorAction SilentlyContinue | ForEach-Object {
    @{
        Name = $_.Name
        DeviceID = $_.DeviceID
        ScreenWidth = $_.ScreenWidth
        ScreenHeight = $_.ScreenHeight
        Status = $_.Status
        Availability = $_.Availability
    }
}
$displays = Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
    @{
        Name = $_.Name
        AdapterRAM_MB = [math]::Round($_.AdapterRAM / 1MB, 0)
        DriverVersion = $_.DriverVersion
        DriverDate = if ($_.DriverDate) { $_.DriverDate.ToString('o') } else { $null }
        VideoMode = $_.VideoModeDescription
        CurrentRefreshRate = $_.CurrentRefreshRate
        Status = $_.Status
    }
}
@{ monitors = $monitors; adapters = $displays } | ConvertTo-Json -Depth 3 -Compress
"""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return [_json.loads(result.stdout.strip())]
        except Exception:
            pass
        return []
